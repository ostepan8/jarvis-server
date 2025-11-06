# agents/nlu_agent.py

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set
import json
import asyncio
import uuid
from ..base import NetworkAgent
from ..message import Message
from ...ai_clients import BaseAIClient
from ...logging import JarvisLogger
from ...utils import extract_json_from_text
from ...utils.performance import track_async


class NLUAgent(NetworkAgent):
    """Natural Language Understanding Agent for processing raw user input
    and delegating to the correct agent based on intent. Now handles direct
    routing and response aggregation for multi-step workflows."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
        response_timeout: float = 30.0,
    ) -> None:
        super().__init__("NLUAgent", logger)
        self.ai_client = ai_client
        self.response_timeout = response_timeout
        # Track active requests: request_id -> {user_input, original_requester, results, step}
        self.active_requests: Dict[str, Dict[str, Any]] = {}

    @property
    def description(self) -> str:
        return (
            "Classifies user messages into intents and routes them to the "
            "appropriate agent using intent_matching. Handles multi-step workflows."
        )

    @property
    def capabilities(self) -> Set[str]:
        # This agent provides a single "intent_matching" capability
        return {"intent_matching"}

    async def _handle_capability_response(self, message: Message) -> None:
        """Handle responses from agents we've routed to."""
        request_id = message.request_id

        # Check if this is a response to an internal request (need to map to parent)
        if request_id in self.active_requests:
            request_info = self.active_requests[request_id]
            # If this has a parent_request_id, it's an internal request - map to parent
            if "parent_request_id" in request_info:
                parent_id = request_info["parent_request_id"]
                self.logger.log(
                    "DEBUG",
                    f"Mapping internal response to parent request",
                    f"internal_id={request_id}, parent_id={parent_id}",
                )
                # Use the parent request_id for the rest of processing
                request_id = parent_id
                request_info = self.active_requests[parent_id]
        else:
            # Not tracked - might be from an agent routing back to us
            self.logger.log(
                "WARNING",
                "NLUAgent received untracked response",
                f"request_id={request_id}, from={message.from_agent}",
            )
            return

        request_info = self.active_requests[request_id]
        request_info.setdefault("agent_results", []).append(
            {
                "from_agent": message.from_agent,
                "result": message.content,
            }
        )

        self.logger.log(
            "INFO",
            f"NLUAgent received response from {message.from_agent}",
            f"request_id={request_id}, step={request_info.get('step', 0)}",
        )

        user_input = request_info.get("user_input", "")
        results = request_info.get("agent_results", [])

        # Check if there are remaining capabilities to execute
        remaining_capabilities = request_info.get("remaining_capabilities", [])

        if remaining_capabilities:
            # Continue with next capability
            next_capability = remaining_capabilities.pop(0)
            request_info["step"] = request_info.get("step", 0) + 1
            request_info["remaining_capabilities"] = remaining_capabilities

            self.logger.log(
                "INFO",
                f"NLU continuing with next capability: {next_capability}",
                f"request_id={request_id}, remaining={len(remaining_capabilities)}",
            )

            # Route to next capability - use NEW internal request_id
            next_internal_id = str(uuid.uuid4())
            await self.request_capability(
                capability=next_capability,
                data={"prompt": user_input, "context": {"previous_results": results}},
                request_id=next_internal_id,
            )
            # Track the internal request
            self.active_requests[next_internal_id] = {
                "parent_request_id": request_id,
                "user_input": user_input,
            }
            return

        # Check if agent indicated more work is needed
        agent_result = message.content
        if isinstance(agent_result, dict) and agent_result.get("needs_followup"):
            # Agent wants to route to another agent
            followup_capability = agent_result.get("followup_capability")
            if (
                followup_capability
                and followup_capability in self.network.capability_registry
            ):
                self.logger.log(
                    "INFO",
                    f"Agent requested follow-up to {followup_capability}",
                    f"request_id={request_id}",
                )
                request_info["step"] = request_info.get("step", 0) + 1
                # Use NEW internal request_id for follow-up
                followup_internal_id = str(uuid.uuid4())
                await self.request_capability(
                    capability=followup_capability,
                    data={
                        "prompt": agent_result.get("followup_prompt", user_input),
                        "context": {"previous_results": results},
                    },
                    request_id=followup_internal_id,
                )
                # Track the internal request
                self.active_requests[followup_internal_id] = {
                    "parent_request_id": request_id,
                    "user_input": user_input,
                }
                return

        # All done - format and send final response
        original_requester = request_info.get("original_requester")
        if original_requester:
            try:
                # Format final response
                self.logger.log(
                    "INFO",
                    f"Formatting final response for request {request_id}",
                    f"original_requester={original_requester}, results_count={len(results)}",
                )

                final_response = await self._format_final_response(user_input, results)

                response_preview = (
                    final_response[:100]
                    if len(final_response) > 100
                    else final_response
                )
                self.logger.log(
                    "INFO",
                    f"Final response formatted: {response_preview}",
                    f"request_id={request_id}",
                )

                # Respond to original requester
                self.logger.log(
                    "INFO",
                    f"Sending final response to {original_requester}",
                    f"request_id={request_id}",
                )

                await self.send_capability_response(
                    to_agent=original_requester,
                    result={"response": final_response, "results": results},
                    request_id=request_id,
                    original_message_id=message.id,
                )

                self.logger.log(
                    "INFO",
                    f"Final response sent to {original_requester}",
                    f"request_id={request_id}",
                )

                # Clean up
                del self.active_requests[request_id]

            except Exception as e:
                self.logger.log(
                    "ERROR",
                    f"Error formatting/sending final response for {request_id}",
                    f"Error: {str(e)}",
                )
                # Try to send error response
                try:
                    await self.send_capability_response(
                        to_agent=original_requester,
                        result={"response": f"Error: {str(e)}", "results": results},
                        request_id=request_id,
                        original_message_id=message.id,
                    )
                except Exception as send_error:
                    self.logger.log(
                        "ERROR",
                        f"Failed to send error response: {str(send_error)}",
                        "",
                    )
                finally:
                    # Clean up even on error
                    if request_id in self.active_requests:
                        del self.active_requests[request_id]
        else:
            self.logger.log(
                "WARNING",
                f"No original_requester found for request {request_id}",
                f"request_info={request_info}",
            )

    async def _handle_capability_request(self, message: Message) -> None:
        if message.content.get("capability") != "intent_matching":
            return

        user_input = message.content["data"]["input"]
        context = message.content["data"].get("context", {})
        request_id = message.request_id
        original_requester = message.from_agent
        # Extract allowed_agents from the capability request (passed through network)
        allowed_agents = message.content.get("allowed_agents")

        self.logger.log("INFO", "NLU received input", user_input)

        known_capabilities = list(self.network.capability_registry.keys())

        # Classify the request
        classification = await self.classify(user_input, known_capabilities, context)

        # Handle different intents
        if classification.get("intent") == "perform_capability":
            capability = classification.get("capability")
            if capability and capability in self.network.capability_registry:
                # Create a NEW request_id for the internal routing to avoid overwriting
                # the original future that JarvisSystem is waiting for
                internal_request_id = str(uuid.uuid4())

                # Track this request using the ORIGINAL request_id (for final response)
                self.active_requests[request_id] = {
                    "user_input": user_input,
                    "original_requester": original_requester,
                    "agent_results": [],
                    "step": 1,
                    "original_message_id": message.id,
                    "internal_request_id": internal_request_id,  # Track internal ID
                }

                # Route directly to the agent using the INTERNAL request_id
                providers = self.network.capability_registry[capability]
                if providers:
                    target_agent = providers[0]
                    self.logger.log(
                        "INFO",
                        f"NLU routing to {target_agent} for capability '{capability}'",
                        f"original_request_id={request_id}, internal_request_id={internal_request_id}",
                    )

                    # Request the capability from the target agent using INTERNAL ID
                    await self.request_capability(
                        capability=capability,
                        data={"prompt": user_input, "context": context},
                        request_id=internal_request_id,  # Use internal ID!
                        allowed_agents=set(allowed_agents) if allowed_agents else None,
                    )
                    # Also track the internal request so we can map responses back
                    self.active_requests[internal_request_id] = {
                        "parent_request_id": request_id,  # Link to original
                        "user_input": user_input,
                    }
                    # Response will be handled in _handle_capability_response
                else:
                    self.logger.log(
                        "WARNING", f"No providers found for capability '{capability}'"
                    )
                    await self.send_error(
                        original_requester,
                        f"No agent available for capability '{capability}'",
                        request_id,
                    )
            else:
                self.logger.log(
                    "WARNING", f"Invalid capability in classification: {capability}"
                )
                await self.send_error(
                    original_requester,
                    f"Could not understand the request: no valid capability found",
                    request_id,
                )

        elif classification.get("intent") == "chat":
            # Route to ChatAgent - use internal request_id
            capability = "chat"
            internal_request_id = str(uuid.uuid4())
            self.active_requests[request_id] = {
                "user_input": user_input,
                "original_requester": original_requester,
                "agent_results": [],
                "step": 1,
                "original_message_id": message.id,
                "internal_request_id": internal_request_id,
            }
            await self.request_capability(
                capability=capability,
                data={"prompt": user_input, "context": context},
                request_id=internal_request_id,  # Use internal ID
                allowed_agents=set(allowed_agents) if allowed_agents else None,
            )
            # Track internal request
            self.active_requests[internal_request_id] = {
                "parent_request_id": request_id,
                "user_input": user_input,
            }

        elif classification.get("intent") == "run_protocol":
            # For protocols, return classification for system to handle
            await self.send_capability_response(
                to_agent=original_requester,
                result=classification,
                request_id=request_id,
                original_message_id=message.id,
            )

        else:
            # Unknown intent or complex multi-step - handle via multi-step routing
            # Try to break down into capabilities
            capabilities_needed = await self._extract_capabilities(
                user_input, known_capabilities
            )

            if not capabilities_needed:
                await self.send_error(
                    original_requester,
                    "Could not understand the request. Please try rephrasing.",
                    request_id,
                )
                return

            # Route to first capability, track the rest - use internal request_id
            internal_request_id = str(uuid.uuid4())
            self.active_requests[request_id] = {
                "user_input": user_input,
                "original_requester": original_requester,
                "agent_results": [],
                "remaining_capabilities": (
                    capabilities_needed[1:] if len(capabilities_needed) > 1 else []
                ),
                "step": 1,
                "original_message_id": message.id,
                "internal_request_id": internal_request_id,
            }

            first_capability = capabilities_needed[0]
            await self.request_capability(
                capability=first_capability,
                data={"prompt": user_input, "context": context},
                request_id=internal_request_id,  # Use internal ID
                allowed_agents=set(allowed_agents) if allowed_agents else None,
            )
            # Track internal request
            self.active_requests[internal_request_id] = {
                "parent_request_id": request_id,
                "user_input": user_input,
            }

    @track_async("nlu_reasoning")
    async def classify(
        self,
        user_input: str,
        capabilities: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Invoke the LLM to classify the user_input into a routing JSON."""
        prompt = self.build_prompt(user_input, capabilities, context)
        self.logger.log("DEBUG", "NLU prompt built", prompt)

        response = await self.ai_client.weak_chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input},
            ],
            [],
        )
        content = response[0].content
        self.logger.log("INFO", "NLU raw model output", content)

        classification = extract_json_from_text(content)
        if classification:
            classification["target_agent"] = ""

        valid_intents = {
            "perform_capability",
            "chat",
            "run_protocol",
            "define_protocol",
            "ask_about_protocol",
        }

        if classification is None:
            # Fallback: try to find a matching capability
            classification = {"intent": None, "capability": None}

        if classification and classification.get("intent") not in valid_intents:
            if classification.get("capability") in capabilities:
                classification["intent"] = "perform_capability"
            else:
                classification["intent"] = None  # Will trigger multi-step handling

        # CHAT INTENT: Route to ChatAgent
        if classification.get("intent") == "chat":
            classification["target_agent"] = "ChatAgent"
            self.logger.log(
                "INFO",
                "Routing to ChatAgent for chat intent",
                classification,
            )

        if classification.get("intent") == "perform_capability":
            requested_capability = classification.get("capability")
            if requested_capability and requested_capability not in capabilities:
                self.logger.log(
                    "WARNING",
                    f"LLM requested non-existent capability '{requested_capability}'",
                    f"Available capabilities: {capabilities}",
                )
                classification["intent"] = None  # Will trigger multi-step handling

        return classification

    async def _extract_capabilities(
        self, user_input: str, available_capabilities: List[str]
    ) -> List[str]:
        """Extract multiple capabilities from a user request."""
        # Use LLM to identify multiple capabilities needed
        prompt = f"""Analyze this request and identify ALL capabilities needed (in order if sequential):

Request: "{user_input}"

Available capabilities: {', '.join(available_capabilities)}

Return JSON with a list of capability names, in order if they need to run sequentially:
{{"capabilities": ["capability1", "capability2", ...]}}

If only one capability is needed, return a single-item list."""

        try:
            response = await self.ai_client.weak_chat(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_input},
                ],
                [],
            )
            result = extract_json_from_text(response[0].content)
            if result and "capabilities" in result:
                # Filter to only include valid capabilities
                valid = [
                    c for c in result["capabilities"] if c in available_capabilities
                ]
                return valid
        except Exception as e:
            self.logger.log("ERROR", "Failed to extract capabilities", str(e))

        return []

    async def _format_final_response(
        self, user_input: str, agent_results: List[Dict[str, Any]]
    ) -> str:
        """Format a natural language response from agent results."""
        if not agent_results:
            self.logger.log("DEBUG", "No agent results, using default response", "")
            return "I completed your request."

        self.logger.log(
            "DEBUG",
            f"Formatting response from {len(agent_results)} agent result(s)",
            "",
        )

        # Use LLM to format a natural response
        system_prompt = (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Format a natural, conversational response based on the agent results below. "
            "Keep it concise and direct. Don't use bullet points or lists - "
            "write in flowing prose."
        )

        results_summary = json.dumps(agent_results, indent=2)

        user_content = (
            f"Original request: '{user_input}'\n\n"
            f"Agent results:\n{results_summary}\n\n"
            "Provide a natural response:"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            self.logger.log("DEBUG", "Calling AI client to format response", "")
            response = await self.ai_client.weak_chat(messages, [])
            formatted = (
                response[0].content
                if hasattr(response[0], "content")
                else str(response[0])
            )
            self.logger.log("DEBUG", f"AI formatted response: {formatted[:100]}", "")
            return formatted
        except Exception as e:
            self.logger.log(
                "ERROR", f"Failed to format response with LLM: {str(e)}", ""
            )
            import traceback

            self.logger.log("ERROR", "Traceback", traceback.format_exc())
            # Fallback: extract useful info from results
            try:
                # Try to extract useful information from agent results
                if agent_results:
                    first_result = agent_results[0].get("result", {})
                    if isinstance(first_result, dict):
                        status = first_result.get("status", "")
                        action = first_result.get("action", "")
                        if status or action:
                            return f"I've {action or status.lower()}."
                return f"I've completed your request: {user_input}"
            except Exception as fallback_error:
                self.logger.log(
                    "ERROR", f"Fallback formatting failed: {str(fallback_error)}", ""
                )
                return f"I've completed your request."

    def build_prompt(
        self,
        user_input: str,
        capabilities: List[str],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        cap_list = ", ".join(capabilities) if capabilities else "none"
        context_str = ""
        if context:
            context_str = (
                f"\n\n**Context from previous steps:**\n{json.dumps(context, indent=2)}"
            )

        prompt = f"""You are JARVIS's Natural Language Understanding engine.

Your job is to analyze the user input and return **only** a JSON object—no prose, no explanations.

**CRITICAL RULES:**
1. You can ONLY use capabilities from the "Available Capabilities" list below
2. DO NOT invent capability names
3. Prefer these intents:
   - "perform_capability" = Execute ONE single capability
   - "chat" = General conversation that doesn't require specific capabilities
   - "run_protocol" = Matches a predefined protocol/command
DO NOT USE "orchestrate_tasks" - that's deprecated.

**Decision Logic:**
- Does the user want ONE simple action that matches ONE capability? → "perform_capability"
- Is this general conversation? → "chat"
- Does it match a known protocol pattern? → "run_protocol"
- Not sure? Default to "perform_capability" if it matches any single capability

**User Input**
\"\"\"{user_input}\"\"\"
{context_str}

**Available Capabilities:**
{cap_list}

**Examples:**
- "Turn on the lights" → {{"intent": "perform_capability", "capability": "control_lights"}}
- "Schedule a meeting" → {{"intent": "perform_capability", "capability": "schedule_appointment"}}
- "What's the weather?" → {{"intent": "perform_capability", "capability": "get_weather"}}
- "How are you?" → {{"intent": "chat", "capability": null}}

**Return ONLY this JSON:**
{{
  "intent": "perform_capability OR chat OR run_protocol",
  "capability": "exact_capability_name_from_list OR null",
}}"""
        return prompt
