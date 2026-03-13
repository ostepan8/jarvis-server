# agents/nlu_agent.py

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING
import json
from ..base import NetworkAgent
from ..message import Message
from ...ai_clients import BaseAIClient
from ...logging import JarvisLogger
from ...utils import extract_json_from_text
from ...utils.performance import track_async

if TYPE_CHECKING:
    from .fast_classifier import FastPathClassifier


class ClassificationCache:
    """Simple dict-based cache with TTL for classification results."""

    def __init__(self, ttl: float = 120.0, max_size: int = 500) -> None:
        self._cache: Dict[str, tuple[Dict[str, Any], float]] = {}
        self._ttl = ttl
        self._max_size = max_size

    def _normalize_key(self, user_input: str) -> str:
        return user_input.lower().strip()

    def get(self, user_input: str) -> Optional[Dict[str, Any]]:
        key = self._normalize_key(user_input)
        if key in self._cache:
            result, timestamp = self._cache[key]
            if time.time() - timestamp < self._ttl:
                return result
            else:
                del self._cache[key]
        return None

    def put(self, user_input: str, classification: Dict[str, Any]) -> None:
        key = self._normalize_key(user_input)
        if len(self._cache) >= self._max_size:
            oldest_key = min(self._cache, key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
        self._cache[key] = (classification, time.time())

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


class NLUAgent(NetworkAgent):
    """Natural Language Understanding Agent for processing raw user input
    and delegating to the correct agent based on intent. Uses a unified
    DAG-based classification and supports fast-path embedding matching."""

    def __init__(
        self,
        ai_client: BaseAIClient,
        logger: Optional[JarvisLogger] = None,
        response_timeout: float = 30.0,
        fast_classifier: Optional[FastPathClassifier] = None,
        cache_ttl: float = 120.0,
        cache_max_size: int = 500,
    ) -> None:
        super().__init__("NLUAgent", logger)
        self.ai_client = ai_client
        self.response_timeout = response_timeout
        self.fast_classifier = fast_classifier
        self._classification_cache = ClassificationCache(
            ttl=cache_ttl, max_size=cache_max_size
        )
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
            capability_data = {
                "prompt": user_input,
                "context": {"previous_results": results},
            }
            seq_user_id = request_info.get("user_id")
            if seq_user_id is not None:
                capability_data["user_id"] = seq_user_id
            await self.request_capability(
                capability=next_capability,
                data=capability_data,
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
                capability_data = {
                    "prompt": agent_result.get("followup_prompt", user_input),
                    "context": {"previous_results": results},
                }
                followup_user_id = request_info.get("user_id")
                if followup_user_id is not None:
                    capability_data["user_id"] = followup_user_id
                await self.request_capability(
                    capability=followup_capability,
                    data=capability_data,
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

                final_response = self._build_final_response(user_input, results)

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

                # Check if any agent results indicate failure
                has_errors = False
                error_info = None
                for result in results:
                    result_data = result.get("result", {})
                    if isinstance(result_data, dict):
                        # Check for explicit success=False
                        if result_data.get("success") is False:
                            has_errors = True
                            error_info = result_data.get("error")
                            break
                        # Check for error field presence
                        if "error" in result_data:
                            has_errors = True
                            error_info = result_data.get("error")
                            break

                # Build response with proper error propagation
                if has_errors:
                    response_payload = {
                        "response": final_response,
                        "results": results,
                        "success": False,
                    }
                    if error_info:
                        response_payload["error"] = error_info
                else:
                    response_payload = {
                        "response": final_response,
                        "results": results,
                        "success": True,
                    }

                await self.send_capability_response(
                    to_agent=original_requester,
                    result=response_payload,
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

    async def _handle_error(self, message: Message) -> None:
        """Handle error messages from agents and propagate them back to the requester."""
        request_id = message.request_id
        error_content = message.content.get("error", "Unknown error")

        self.logger.log(
            "ERROR",
            f"Error from {message.from_agent}",
            f"{error_content}",
        )

        # Look up the original requester for this request
        # Try direct match first, then check for sub-requests (format: "parent_id:capability")
        request_info = self.active_requests.get(request_id)
        if not request_info and ":" in request_id:
            # This might be a sub-request, try to find parent
            parent_id = request_id.split(":", 1)[0]
            request_info = self.active_requests.get(parent_id)
            if request_info:
                # Use parent request_id for response
                request_id = parent_id

        if request_info:
            original_requester = request_info.get("original_requester")
            if original_requester:
                # Send error response back to original requester
                await self.send_capability_response(
                    to_agent=original_requester,
                    result={
                        "response": f"Error: {error_content}",
                        "success": False,
                        "error": {"message": error_content, "error_type": "AgentError"},
                    },
                    request_id=request_id,
                    original_message_id=message.id,
                )

                # Clean up
                if request_id in self.active_requests:
                    del self.active_requests[request_id]
            else:
                self.logger.log(
                    "ERROR",
                    f"NLUAgent message handling error: 'original_requester'",
                    f"request_id={request_id}, request_info={list(request_info.keys())}",
                )
        else:
            self.logger.log(
                "WARNING",
                f"Received error for unknown request {request_id}",
                f"error={error_content}",
            )

    async def _handle_capability_request(self, message: Message) -> None:
        if message.content.get("capability") != "intent_matching":
            return

        user_input = message.content["data"]["input"]
        context = message.content["data"].get("context", {})
        conversation_history = message.content["data"].get("conversation_history", [])
        user_id = message.content["data"].get("user_id")
        request_id = message.request_id
        original_requester = message.from_agent
        allowed_agents = message.content.get("allowed_agents")

        self.logger.log("INFO", "NLU received input", user_input)

        if conversation_history:
            context["conversation_history"] = conversation_history

        known_capabilities = list(self.network.capability_registry.keys())

        # ---- Classification pipeline: fast-path → cache → LLM ----
        classification: Optional[Dict[str, Any]] = None

        # Step 1: Try fast-path embedding classifier
        if self.fast_classifier:
            fast_result = await self.fast_classifier.classify(user_input)
            if fast_result["confidence"] == "high":
                cap = fast_result["capability"]
                if cap in known_capabilities or cap == "chat":
                    classification = {"dag": {cap: []}}
                    self.logger.log(
                        "INFO",
                        f"Fast-path classification: {cap}",
                        f"score={fast_result['score']:.3f}",
                    )

        # Step 2: Try cache
        if classification is None:
            cached = self._classification_cache.get(user_input)
            if cached is not None:
                classification = cached
                self.logger.log("INFO", "Classification cache hit", user_input[:50])

        # Step 3: LLM classification (unified — always returns DAG)
        if classification is None:
            hint = None
            if self.fast_classifier:
                fast_result = await self.fast_classifier.classify(user_input)
                if fast_result.get("confidence") == "medium":
                    hint = fast_result.get("hint_capabilities")
            classification = await self.classify(
                user_input, known_capabilities, context, conversation_history, hint=hint
            )
            # Cache non-chat classifications
            dag = classification.get("dag", {})
            if dag and "chat" not in dag:
                self._classification_cache.put(user_input, classification)

        # ---- Route based on classification ----

        # Protocol intent passthrough
        if classification.get("intent") == "run_protocol":
            await self.send_capability_response(
                to_agent=original_requester,
                result=classification,
                request_id=request_id,
                original_message_id=message.id,
            )
            return

        # Everything else is DAG-based
        dag = classification.get("dag", {})
        if not dag:
            await self.send_error(
                original_requester,
                "Could not understand the request. Please try rephrasing.",
                request_id,
            )
            return

        # Single-capability DAG → simplified direct routing
        if len(dag) == 1:
            capability = list(dag.keys())[0]
            self.active_requests[request_id] = {
                "user_input": user_input,
                "original_requester": original_requester,
                "user_id": user_id,
                "agent_results": [],
                "step": 1,
                "original_message_id": message.id,
                "current_capability": capability,
            }

            self.logger.log(
                "INFO",
                f"NLU routing to capability '{capability}'",
                f"request_id={request_id}",
            )

            capability_data: Dict[str, Any] = {"prompt": user_input, "context": context}
            if user_id is not None:
                capability_data["user_id"] = user_id
            await self.request_capability(
                capability=capability,
                data=capability_data,
                request_id=request_id,
                allowed_agents=set(allowed_agents) if allowed_agents else None,
            )
            return

        # Multi-capability DAG → parallel execution
        completed_caps: Set[str] = set()
        running_caps: Set[str] = set()
        capability_request_ids: Dict[str, str] = {}

        self.active_requests[request_id] = {
            "user_input": user_input,
            "original_requester": original_requester,
            "user_id": user_id,
            "agent_results": [],
            "dag": dag,
            "completed_caps": completed_caps,
            "running_caps": running_caps,
            "capability_request_ids": capability_request_ids,
            "original_message_id": message.id,
            "context": context,
            "allowed_agents": set(allowed_agents) if allowed_agents else None,
        }

        await self._execute_ready_capabilities(
            request_id, dag, user_input, context, allowed_agents,
        )

    @track_async("nlu_reasoning")
    async def classify(
        self,
        user_input: str,
        capabilities: List[str],
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        hint: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Unified classification: one LLM call that always returns a DAG.

        Returns either:
          {"dag": {"capability": [deps], ...}}
          {"intent": "run_protocol", ...}
        """
        prompt = self._build_unified_prompt(
            user_input, capabilities, context, conversation_history, hint
        )
        self.logger.log("DEBUG", "NLU unified prompt built", prompt)

        response = await self.ai_client.weak_chat(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_input},
            ],
            [],
        )
        content = response[0].content
        self.logger.log("INFO", "NLU raw model output", content)

        result = extract_json_from_text(content)
        if not result:
            return {"dag": {"chat": []}}

        return self._normalize_classification(result, capabilities)

    def _normalize_classification(
        self, result: Dict[str, Any], capabilities: List[str]
    ) -> Dict[str, Any]:
        """Validate and normalize LLM classification output into canonical DAG form."""
        # Protocol intent passthrough
        if result.get("intent") == "run_protocol":
            return result

        # Handle legacy format (intent/capability without dag)
        if "dag" not in result:
            intent = result.get("intent")
            capability = result.get("capability")
            if intent == "chat" or (intent is None and capability is None):
                return {"dag": {"chat": []}}
            if capability and (capability in capabilities or capability == "chat"):
                return {"dag": {capability: []}}
            return {"dag": {"chat": []}}

        # Validate DAG capabilities
        dag = result["dag"]
        if not isinstance(dag, dict):
            return {"dag": {"chat": []}}

        filtered_dag: Dict[str, List[str]] = {}
        for cap, deps in dag.items():
            if cap in capabilities or cap == "chat":
                valid_deps = [
                    d for d in (deps if isinstance(deps, list) else [])
                    if (d in capabilities or d == "chat") and d != cap
                ]
                filtered_dag[cap] = valid_deps

        if not filtered_dag:
            return {"dag": {"chat": []}}

        if not self._validate_dag(filtered_dag):
            self.logger.log(
                "WARNING",
                "Invalid DAG (circular deps), falling back to parallel",
                str(filtered_dag),
            )
            return {"dag": {cap: [] for cap in filtered_dag.keys()}}

        return {"dag": filtered_dag}

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
            # Copy original_requester from parent request
            parent_request_info = self.active_requests.get(request_id, {})
            self.active_requests[sub_request_id] = {
                "parent_request_id": request_id,  # For correlation
                "capability": cap,
                "user_input": user_input,
                "current_capability": cap,
                "original_requester": parent_request_info.get("original_requester"),
                "user_id": parent_request_info.get("user_id"),
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
            capability_data = {"prompt": user_input, "context": enhanced_context}
            dag_user_id = request_info.get("user_id")
            if dag_user_id is not None:
                capability_data["user_id"] = dag_user_id
            await self.request_capability(
                capability=cap,
                data=capability_data,
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

            # Multi-cap DAGs benefit from LLM synthesis for coherent prose
            try:
                final_response = await self._format_final_response_llm(
                    user_input, results
                )
            except Exception:
                final_response = self._build_final_response(user_input, results)

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

    def _build_final_response(
        self, user_input: str, agent_results: List[Dict[str, Any]]
    ) -> str:
        """Build final response from agent results without an LLM call.

        Agents already return natural language in their 'response' field
        via the AgentResponse contract. For single results, pass through
        directly. For multiple results, join them.
        """
        if not agent_results:
            return "I completed your request."

        responses: List[str] = []
        for entry in agent_results:
            result_data = entry.get("result", {})
            if isinstance(result_data, dict):
                text = result_data.get("response") or result_data.get("message", "")
                if text:
                    responses.append(text)

        if not responses:
            return "I completed your request."
        if len(responses) == 1:
            return responses[0]
        return "\n\n".join(responses)

    async def _format_final_response_llm(
        self, user_input: str, agent_results: List[Dict[str, Any]]
    ) -> str:
        """LLM-based response formatting (kept as fallback, not called by default)."""
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

    def _build_unified_prompt(
        self,
        user_input: str,
        capabilities: List[str],
        context: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        hint: Optional[List[str]] = None,
    ) -> str:
        """Build the unified classification prompt that always returns a DAG."""
        cap_list = ", ".join(capabilities) if capabilities else "none"

        history_str = ""
        if conversation_history and len(conversation_history) > 0:
            history_str = "\n\n**Recent Conversation History:**\n"
            for i, turn in enumerate(conversation_history[-5:], 1):
                history_str += f"{i}. User: {turn.get('user', '')}\n"
                history_str += f"   Assistant: {turn.get('assistant', '')}\n"
            history_str += (
                "\n**IMPORTANT:** If the user's input is a brief response "
                "(like 'Yes', 'No', 'OK', etc.), use the conversation history "
                "to understand what they're responding to.\n"
            )

        context_str = ""
        if context:
            filtered_context = {
                k: v for k, v in context.items() if k != "conversation_history"
            }
            if filtered_context:
                context_str = f"\n\n**Context from previous steps:**\n{json.dumps(filtered_context, indent=2)}"

        hint_str = ""
        if hint:
            hint_str = f"\n\n**Hint:** The input is likely related to: {', '.join(hint)}. Confirm or override."

        prompt = f"""You are JARVIS's Natural Language Understanding engine.

Analyze the user input and return **only** a JSON object — no prose, no explanations.

**RESPONSE FORMAT — always return a DAG:**
{{"dag": {{"capability_name": [list_of_dependency_capabilities]}}}}

Special cases:
- Chat/conversation: {{"dag": {{"chat": []}}}}
- Protocol match: {{"intent": "run_protocol", "protocol": "protocol_name"}}
- Single capability: {{"dag": {{"capability_name": []}}}}
- Multiple independent: {{"dag": {{"cap1": [], "cap2": []}}}}
- Dependent capabilities: {{"dag": {{"cap1": [], "cap2": ["cap1"]}}}}

**RULES (IN ORDER OF PRIORITY):**

1. You can ONLY use capabilities from the Available Capabilities list below. DO NOT invent names.

2. **CONDITIONAL LOGIC (HIGHEST PRIORITY):**
   If the request contains conditional words ("if", "then", "else", "when", "based on",
   "depending on", "otherwise") AND the condition depends on a result from another action:
   → Return a DAG with the question capability first, conditional action depending on it.
   **CRITICAL:** Even if it starts with "search for" or "find", if it contains conditional
   logic that depends on the search result, return a multi-capability DAG.

3. **GENERAL KNOWLEDGE vs USER-SPECIFIC:**
   - General knowledge (facts, history, science, "what is", "who is", "when did"):
     → ALWAYS use "search" capability (NEVER "chat", "search_facts", or "get_facts")
   - User-specific ("my favorite", "what I mentioned", "what did I say"):
     → Use "search_facts" or "get_facts"
   - Memory vault management ("browse memories", "memory stats", "consolidate",
     "promote memory"): → Use "browse_memories", "memory_stats",
     "consolidate_memories", or "promote_memory"

4. **MULTIPLE ACTIONS:**
   Multiple distinct actions connected by "and", "also", or targeting different systems:
   → Return DAG with all capabilities. Independent ones get empty deps, dependent ones list deps.

5. **SINGLE ACTION:**
   One clear capability match → {{"dag": {{"capability_name": []}}}}

6. **PROTOCOL MATCH:**
   Matches a known protocol → {{"intent": "run_protocol", "protocol": "name"}}

7. **CHAT (DEFAULT):**
   General conversation, greetings, chit-chat → {{"dag": {{"chat": []}}}}

**User Input:** \"\"\"{user_input}\"\"\"{history_str}{context_str}{hint_str}

**Available Capabilities:** {cap_list}

**EXAMPLES:**
- "Turn on the lights" → {{"dag": {{"lights_on": []}}}}
- "What's the weather?" → {{"dag": {{"search": []}}}}
- "How are you?" → {{"dag": {{"chat": []}}}}
- "What's the capital of Illinois?" → {{"dag": {{"search": []}}}}
- "What's my favorite color?" → {{"dag": {{"search_facts": []}}}}
- "Schedule a meeting" → {{"dag": {{"schedule_appointment": []}}}}
- "Pause tv and make lights red" → {{"dag": {{"roku_pause": [], "lights_color": []}}}}
- "Turn on lights and search for something" → {{"dag": {{"lights_on": [], "search": []}}}}
- "Search for weather and if sunny make lights red" → {{"dag": {{"search": [], "lights_color": ["search"]}}}}
- "When did X come out. if in 2018 make lights blue" → {{"dag": {{"search": [], "lights_color": ["search"]}}}}
- "Search for X and if above Y make lights blue else red" → {{"dag": {{"search": [], "lights_color": ["search"]}}}}
- "Add a Spotify agent" → {{"dag": {{"implement_feature": []}}}}
- "Fix the NLU timeout bug" → {{"dag": {{"fix_bug": []}}}}
- "Write tests for the memory agent" → {{"dag": {{"write_tests": []}}}}
- "How does the protocol system work?" → {{"dag": {{"explain_code": []}}}}
- "Refactor the agent factory" → {{"dag": {{"refactor_code": []}}}}
- "Add a task to fix the login page" → {{"dag": {{"create_task": []}}}}
- "Show my tasks" → {{"dag": {{"list_tasks": []}}}}
- "Mark task abc123 as done" → {{"dag": {{"complete_task": []}}}}
- "What's on my todo list" → {{"dag": {{"list_tasks": []}}}}
- "Delete task abc123" → {{"dag": {{"delete_task": []}}}}
- "Update task abc123 priority to high" → {{"dag": {{"update_task": []}}}}
- "Is the system healthy?" → {{"dag": {{"system_health_check": []}}}}
- "What's down?" → {{"dag": {{"system_health_check": []}}}}
- "Show health report" → {{"dag": {{"health_report": []}}}}
- "Show dependency map" → {{"dag": {{"dependency_map": []}}}}
- "List incidents" → {{"dag": {{"incident_list": []}}}}
- "Browse my memories" → {{"dag": {{"browse_memories": []}}}}
- "Show memory stats" → {{"dag": {{"memory_stats": []}}}}
- "Consolidate my preferences" → {{"dag": {{"consolidate_memories": []}}}}
- "Promote that memory to long-term" → {{"dag": {{"promote_memory": []}}}}
- "How's the machine doing?" → {{"dag": {{"device_status": []}}}}
- "Check CPU and memory usage" → {{"dag": {{"device_status": []}}}}
- "What's eating all my RAM?" → {{"dag": {{"device_diagnostics": []}}}}
- "Show top processes" → {{"dag": {{"device_diagnostics": []}}}}
- "Clean up temp files" → {{"dag": {{"device_cleanup": []}}}}
- "Is the disk almost full?" → {{"dag": {{"device_status": []}}}}
- "Has CPU been high all day?" → {{"dag": {{"device_history": []}}}}
- "Show memory trends" → {{"dag": {{"device_history": []}}}}
- "What were thermals like overnight?" → {{"dag": {{"device_history": []}}}}
- "Start the calendar server" → {{"dag": {{"start_server": []}}}}
- "Stop the API" → {{"dag": {{"stop_server": []}}}}
- "Restart grafana" → {{"dag": {{"restart_server": []}}}}
- "Is the calendar server running?" → {{"dag": {{"server_status": []}}}}
- "Show all servers" → {{"dag": {{"list_servers": []}}}}
- "Wake me up at 7am" → {{"dag": {{"schedule_task": []}}}}
- "Every morning give me the weather" → {{"dag": {{"schedule_task": []}}}}
- "Check health every 30 minutes" → {{"dag": {{"schedule_task": []}}}}
- "Show my schedules" → {{"dag": {{"list_schedules": []}}}}
- "Cancel the morning alarm" → {{"dag": {{"cancel_schedule": []}}}}
- "Pause the weather check" → {{"dag": {{"pause_schedule": []}}}}
- "Resume my alarms" → {{"dag": {{"resume_schedule": []}}}}

Return ONLY the JSON."""
        return prompt
