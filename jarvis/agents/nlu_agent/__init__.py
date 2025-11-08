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

        # Simplified: Handle sub-requests (format: "parent_id:capability") and direct requests
        # Check if this is a sub-request (DAG execution)
        if ":" in request_id:
            # Sub-request format: "parent_id:capability"
            parent_id, capability = request_id.split(":", 1)
            if parent_id in self.active_requests:
                request_info = self.active_requests[parent_id]
                correlation_id = parent_id
            else:
                # Try direct match
                if request_id in self.active_requests:
                    request_info = self.active_requests[request_id]
                    correlation_id = request_id
                    capability = request_info.get("current_capability")
                else:
                    self.logger.log(
                        "WARNING",
                        "NLUAgent received untracked sub-request response",
                        f"request_id={request_id}, from={message.from_agent}",
                    )
                    return
        else:
            # Direct request
            if request_id in self.active_requests:
                request_info = self.active_requests[request_id]
                correlation_id = request_id
                capability = request_info.get("current_capability")
            else:
                self.logger.log(
                    "WARNING",
                    "NLUAgent received untracked response",
                    f"request_id={request_id}, from={message.from_agent}",
                )
                return

        # Add result to agent_results
        request_info.setdefault("agent_results", []).append(
            {
                "from_agent": message.from_agent,
                "capability": capability,
                "result": message.content,
            }
        )

        self.logger.log(
            "INFO",
            f"NLUAgent received response from {message.from_agent}",
            f"request_id={request_id}, correlation_id={correlation_id}, capability={capability}",
        )

        # Use correlation_id (parent request) for all processing
        request_id = correlation_id

        # Check if this is DAG-based execution
        dag = request_info.get("dag")
        if dag is not None:
            # DAG-based execution
            if capability:
                completed_caps = request_info.get("completed_caps", set())
                running_caps = request_info.get("running_caps", set())

                # Mark capability as completed
                completed_caps.add(capability)
                running_caps.discard(capability)

                self.logger.log(
                    "INFO",
                    f"Capability '{capability}' completed in DAG",
                    f"Completed: {len(completed_caps)}/{len(dag)}, Running: {len(running_caps)}",
                )

                # Check if more capabilities can now run (dependencies satisfied)
                user_input = request_info.get("user_input", "")
                context = request_info.get("context", {})
                allowed_agents = request_info.get("allowed_agents")

                await self._execute_ready_capabilities(
                    request_id,
                    dag,
                    user_input,
                    context,
                    allowed_agents,
                )
            return

        # Legacy sequential execution handling
        user_input = request_info.get("user_input", "")
        results = request_info.get("agent_results", [])

        # Check if there are remaining capabilities to execute
        remaining_capabilities = request_info.get("remaining_capabilities", [])

        if remaining_capabilities:
            # Continue with next capability - use same request_id with correlation
            next_capability = remaining_capabilities.pop(0)
            request_info["step"] = request_info.get("step", 0) + 1
            request_info["remaining_capabilities"] = remaining_capabilities
            request_info["current_capability"] = next_capability

            self.logger.log(
                "INFO",
                f"NLU continuing with next capability: {next_capability}",
                f"request_id={request_id}, remaining={len(remaining_capabilities)}",
            )

            # Route to next capability - use same request_id (simplified)
            await self.request_capability(
                capability=next_capability,
                data={"prompt": user_input, "context": {"previous_results": results}},
                request_id=request_id,  # Reuse same request_id
            )
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
                request_info["current_capability"] = followup_capability
                # Use same request_id for follow-up (simplified)
                await self.request_capability(
                    capability=followup_capability,
                    data={
                        "prompt": agent_result.get("followup_prompt", user_input),
                        "context": {"previous_results": results},
                    },
                    request_id=request_id,  # Reuse same request_id
                )
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
        conversation_history = message.content["data"].get("conversation_history", [])
        request_id = message.request_id
        original_requester = message.from_agent
        # Extract allowed_agents from the capability request (passed through network)
        allowed_agents = message.content.get("allowed_agents")

        self.logger.log("INFO", "NLU received input", user_input)

        # Add conversation history to context so it's passed to agents
        if conversation_history:
            context["conversation_history"] = conversation_history

        known_capabilities = list(self.network.capability_registry.keys())

        # Classify the request - pass conversation history for better context understanding
        classification = await self.classify(
            user_input, known_capabilities, context, conversation_history
        )

        # Handle different intents
        if classification.get("intent") == "perform_capability":
            capability = classification.get("capability")
            if capability and capability in self.network.capability_registry:
                # Simplified: Use same request_id throughout, track current capability
                self.active_requests[request_id] = {
                    "user_input": user_input,
                    "original_requester": original_requester,
                    "agent_results": [],
                    "step": 1,
                    "original_message_id": message.id,
                    "current_capability": capability,  # Track current capability
                }

                # Route directly to the agent using the SAME request_id
                providers = self.network.capability_registry[capability]
                if providers:
                    target_agent = providers[0]
                    self.logger.log(
                        "INFO",
                        f"NLU routing to {target_agent} for capability '{capability}'",
                        f"request_id={request_id}",
                    )

                    # Request the capability from the target agent using SAME request_id
                    await self.request_capability(
                        capability=capability,
                        data={"prompt": user_input, "context": context},
                        request_id=request_id,  # Use same request_id
                        allowed_agents=set(allowed_agents) if allowed_agents else None,
                    )
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
            # Route to ChatAgent - use same request_id
            capability = "chat"
            self.active_requests[request_id] = {
                "user_input": user_input,
                "original_requester": original_requester,
                "agent_results": [],
                "step": 1,
                "original_message_id": message.id,
                "current_capability": capability,
            }
            await self.request_capability(
                capability=capability,
                data={"prompt": user_input, "context": context},
                request_id=request_id,  # Use same request_id
                allowed_agents=set(allowed_agents) if allowed_agents else None,
            )

        elif classification.get("intent") == "run_protocol":
            # For protocols, return classification for system to handle
            await self.send_capability_response(
                to_agent=original_requester,
                result=classification,
                request_id=request_id,
                original_message_id=message.id,
            )

        else:
            # Unknown intent or complex multi-step - handle via DAG-based routing
            # Extract capabilities and build DAG with dependencies
            dag = await self._extract_capabilities(user_input, known_capabilities)

            if not dag:
                await self.send_error(
                    original_requester,
                    "Could not understand the request. Please try rephrasing.",
                    request_id,
                )
                return

            # Initialize DAG tracking structure
            # Track which capabilities are pending, running, and completed
            completed_caps: Set[str] = set()
            running_caps: Set[str] = set()  # Track capabilities currently executing
            capability_request_ids: Dict[str, str] = {}  # Map capability -> request_id

            self.active_requests[request_id] = {
                "user_input": user_input,
                "original_requester": original_requester,
                "agent_results": [],
                "dag": dag,  # Store the full DAG
                "completed_caps": completed_caps,
                "running_caps": running_caps,
                "capability_request_ids": capability_request_ids,
                "original_message_id": message.id,
                "context": context,  # Store context for subsequent executions
                "allowed_agents": set(allowed_agents) if allowed_agents else None,
            }

            # Start initial batch of capabilities (those with no dependencies)
            await self._execute_ready_capabilities(
                request_id,
                dag,
                user_input,
                context,
                allowed_agents,
            )

    @track_async("nlu_reasoning")
    async def classify(
        self,
        user_input: str,
        capabilities: List[str],
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Invoke the LLM to classify the user_input into a routing JSON."""
        prompt = self.build_prompt(
            user_input, capabilities, context, conversation_history
        )
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
    ) -> Dict[str, List[str]]:
        """
        Extract multiple capabilities from a user request and build a DAG.

        Returns a dictionary mapping capability -> list of dependencies.
        Capabilities with no dependencies can run in parallel.
        """
        # Use LLM to identify multiple capabilities needed and their dependencies
        prompt = f"""Analyze this request and identify ALL capabilities needed and their dependencies.

Request: "{user_input}"

Available capabilities: {', '.join(available_capabilities)}

Return JSON with a DAG structure where each capability lists its dependencies:
{{"dag": {{
  "capability1": [],  // No dependencies - can run immediately
  "capability2": [],  // No dependencies - can run in parallel with capability1
  "capability3": ["capability1"]  // Depends on capability1 completing first
}}}}

Rules:
- If two capabilities don't depend on each other, they can run in parallel (empty dependencies)
- Only list dependencies if one capability truly needs the result of another
- For independent tasks (e.g., "turn lights red" and "get weather"), use empty dependencies []
- If only one capability is needed, return single capability with empty dependencies

Example for "turn lights red and tell me the weather":
{{"dag": {{
  "lights_color": [],
  "get_weather": []
}}}}

Example for "pause the tv and make the lights red":
{{"dag": {{
  "roku_pause": [],
  "lights_color": []
}}}}

Example for "book a meeting tomorrow and send me a reminder":
{{"dag": {{
  "schedule_appointment": [],
  "send_message": ["schedule_appointment"]  // Reminder needs meeting details
}}}}"""

        try:
            response = await self.ai_client.weak_chat(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_input},
                ],
                [],
            )
            result = extract_json_from_text(response[0].content)
            if result and "dag" in result:
                dag = result["dag"]
                # Filter to only include valid capabilities and validate dependencies
                filtered_dag: Dict[str, List[str]] = {}
                for cap, deps in dag.items():
                    if cap in available_capabilities:
                        # Filter dependencies to only valid capabilities
                        valid_deps = [
                            d for d in deps if d in available_capabilities and d != cap
                        ]
                        filtered_dag[cap] = valid_deps
                # Validate DAG (no circular dependencies - basic check)
                if self._validate_dag(filtered_dag):
                    return filtered_dag
                else:
                    self.logger.log(
                        "WARNING",
                        "Invalid DAG detected (circular or invalid dependencies), falling back to sequential",
                        str(filtered_dag),
                    )
                    # Fallback to sequential execution
                    return {cap: [] for cap in filtered_dag.keys()}
        except Exception as e:
            self.logger.log("ERROR", "Failed to extract capabilities", str(e))

        return {}

    def _validate_dag(self, dag: Dict[str, List[str]]) -> bool:
        """Validate that the DAG has no circular dependencies."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def has_cycle(cap: str) -> bool:
            visited.add(cap)
            rec_stack.add(cap)

            for dep in dag.get(cap, []):
                if dep not in visited:
                    if has_cycle(dep):
                        return True
                elif dep in rec_stack:
                    return True

            rec_stack.remove(cap)
            return False

        for cap in dag.keys():
            if cap not in visited:
                if has_cycle(cap):
                    return False

        return True

    async def _execute_ready_capabilities(
        self,
        request_id: str,
        dag: Dict[str, List[str]],
        user_input: str,
        context: Dict[str, Any],
        allowed_agents: Optional[Set[str]],
    ) -> None:
        """
        Execute all capabilities that have their dependencies satisfied.
        Capabilities with no dependencies or all dependencies completed can run in parallel.
        """
        request_info = self.active_requests.get(request_id)
        if not request_info:
            return

        completed_caps = request_info.get("completed_caps", set())
        running_caps = request_info.get("running_caps", set())

        # Find capabilities ready to execute (dependencies satisfied and not already running/completed)
        ready_caps = []
        for cap, deps in dag.items():
            if cap in completed_caps or cap in running_caps:
                continue  # Already completed or running
            # Check if all dependencies are completed
            if all(dep in completed_caps for dep in deps):
                ready_caps.append(cap)

        if not ready_caps:
            # No more capabilities to execute - check if we're done
            if len(completed_caps) == len(dag):
                # All capabilities completed, format final response
                await self._complete_dag_execution(request_id)
            return

        # Execute all ready capabilities in parallel
        self.logger.log(
            "INFO",
            f"Executing {len(ready_caps)} capabilities in parallel",
            f"Capabilities: {ready_caps}",
        )

        for cap in ready_caps:
            running_caps.add(cap)
            # Use same request_id with capability tracking (simplified)
            sub_request_id = f"{request_id}:{cap}"  # Simple correlation ID format
            request_info["capability_request_ids"][cap] = sub_request_id

            # Track sub-request with correlation to parent
            self.active_requests[sub_request_id] = {
                "parent_request_id": request_id,  # For correlation
                "capability": cap,
                "user_input": user_input,
                "current_capability": cap,
            }

            # Build context with previous results for dependent capabilities
            enhanced_context = dict(context)
            if completed_caps:
                # Include results from completed capabilities in context
                results = request_info.get("agent_results", [])
                enhanced_context["previous_results"] = [
                    r for r in results if r.get("capability") in completed_caps
                ]

            # Execute capability (non-blocking - they'll run in parallel)
            # Use sub_request_id but responses will correlate back to parent
            await self.request_capability(
                capability=cap,
                data={"prompt": user_input, "context": enhanced_context},
                request_id=sub_request_id,
                allowed_agents=allowed_agents,
            )

    async def _complete_dag_execution(self, request_id: str) -> None:
        """Format and send final response after all capabilities in DAG are complete."""
        request_info = self.active_requests.get(request_id)
        if not request_info:
            return

        original_requester = request_info.get("original_requester")
        if not original_requester:
            self.logger.log(
                "WARNING",
                f"No original_requester found for request {request_id}",
                "",
            )
            return

        try:
            user_input = request_info.get("user_input", "")
            results = request_info.get("agent_results", [])

            self.logger.log(
                "INFO",
                f"All capabilities completed for request {request_id}",
                f"Results count: {len(results)}",
            )

            final_response = await self._format_final_response(user_input, results)

            await self.send_capability_response(
                to_agent=original_requester,
                result={"response": final_response, "results": results},
                request_id=request_id,
                original_message_id=request_info.get("original_message_id"),
            )

            # Clean up
            del self.active_requests[request_id]

        except Exception as e:
            self.logger.log(
                "ERROR",
                f"Error completing DAG execution for {request_id}",
                str(e),
            )
            # Try to send error response
            try:
                await self.send_capability_response(
                    to_agent=original_requester,
                    result={"response": f"Error: {str(e)}", "results": []},
                    request_id=request_id,
                    original_message_id=request_info.get("original_message_id"),
                )
            except Exception as send_error:
                self.logger.log(
                    "ERROR",
                    f"Failed to send error response: {str(send_error)}",
                    "",
                )
            finally:
                if request_id in self.active_requests:
                    del self.active_requests[request_id]

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
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        cap_list = ", ".join(capabilities) if capabilities else "none"

        # Format conversation history separately for better readability
        history_str = ""
        if conversation_history and len(conversation_history) > 0:
            history_str = "\n\n**Recent Conversation History:**\n"
            for i, turn in enumerate(conversation_history[-5:], 1):  # Show last 5 turns
                history_str += f"{i}. User: {turn.get('user', '')}\n"
                history_str += f"   Assistant: {turn.get('assistant', '')}\n"
            history_str += (
                "\n**IMPORTANT:** If the user's input is a brief response "
                "(like 'Yes', 'No', 'OK', etc.), use the conversation history "
                "to understand what they're responding to.\n"
            )

        # Filter out conversation_history from context before displaying
        context_str = ""
        if context:
            filtered_context = {
                k: v for k, v in context.items() if k != "conversation_history"
            }
            if filtered_context:
                context_str = f"\n\n**Context from previous steps:**\n{json.dumps(filtered_context, indent=2)}"

        prompt = f"""You are JARVIS's Natural Language Understanding engine.

Your job is to analyze the user input and return **only** a JSON object—no prose, no explanations.

**CRITICAL RULES:**
1. You can ONLY use capabilities from the "Available Capabilities" list below
2. DO NOT invent capability names
3. Prefer these intents:
   - "perform_capability" = Execute ONE single capability
   - "chat" = General conversation that doesn't require specific capabilities
   - "run_protocol" = Matches a predefined protocol/command
   - null = Multiple capabilities needed (will trigger parallel execution)
DO NOT USE "orchestrate_tasks" - that's deprecated.

**Decision Logic:**
- Does the user want MULTIPLE distinct actions (e.g., "pause tv AND make lights red",
  "turn on lights AND get weather")? → {{"intent": null, "capability": null}}
- Does the user want ONE simple action that matches ONE capability? → "perform_capability"
- Is this general conversation? → "chat"
- Does it match a known protocol pattern? → "run_protocol"
- Not sure? Default to "perform_capability" if it matches any single capability

**Key Indicators of Multiple Capabilities:**
- Words like "and", "also", "then" connecting different actions
- Multiple verbs targeting different systems (e.g., "pause" + "make", "turn on" + "get")
- Different target objects (e.g., "tv" and "lights", "calendar" and "weather")

**User Input**
\"\"\"{user_input}\"\"\"
{history_str}{context_str}

**Available Capabilities:**
{cap_list}

**Examples:**
- "Turn on the lights" → {{"intent": "perform_capability", "capability": "lights_on"}}
- "Pause the tv and make the lights red" → {{"intent": null, "capability": null}}
- "Schedule a meeting" → {{"intent": "perform_capability", "capability": "schedule_appointment"}}
- "What's the weather?" → {{"intent": "perform_capability", "capability": "get_weather"}}
- "Turn on lights and get weather" → {{"intent": null, "capability": null}}
- "How are you?" → {{"intent": "chat", "capability": null}}

**Return ONLY this JSON:**
{{
  "intent": "perform_capability OR chat OR run_protocol OR null",
  "capability": "exact_capability_name_from_list OR null",
}}"""
        return prompt
