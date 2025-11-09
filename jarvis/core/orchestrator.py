"""Request orchestrator for managing user request processing.

This module extracts the complex request processing logic from JarvisSystem
into focused, single-responsibility components.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import nullcontext
from os import getenv
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from .response_logger import ResponseLogger, RequestTimer
from .profile import AgentProfile
from ..utils.performance import PerfTracker, get_tracker

if TYPE_CHECKING:
    from ..agents.agent_network import AgentNetwork
    from ..protocols.runtime import ProtocolRuntime
    from ..logging import JarvisLogger


class RequestMetadata:
    """Container for request metadata extracted from incoming requests."""
    
    def __init__(
        self,
        user_id: int,
        device: Optional[str] = None,
        location: Optional[str] = None,
        source: Optional[str] = None,
        profile: Optional[AgentProfile] = None,
    ):
        self.user_id = user_id
        self.device = device
        self.location = location
        self.source = source
        self.profile = profile


class RequestOrchestrator:
    """Orchestrates user request processing through the agent network.
    
    This class breaks down the monolithic process_request method into
    focused, testable components following single responsibility principle.
    """
    
    def __init__(
        self,
        network: "AgentNetwork",
        protocol_runtime: Optional["ProtocolRuntime"],
        response_logger: ResponseLogger,
        logger: "JarvisLogger",
        response_timeout: float = 15.0,
        max_history_length: int = 10,
    ):
        """Initialize request orchestrator.
        
        Args:
            network: The agent network for communication
            protocol_runtime: Protocol execution runtime
            response_logger: Logger for interactions
            logger: System logger
            response_timeout: Timeout for capability requests
            max_history_length: Maximum conversation history to maintain
        """
        self.network = network
        self.protocol_runtime = protocol_runtime
        self.response_logger = response_logger
        self.logger = logger
        self.response_timeout = response_timeout
        self.max_history_length = max_history_length
        
        # Conversation history: user_id -> list of turns
        self.conversation_history: Dict[int, List[Dict[str, str]]] = {}
        
        # User profiles: user_id -> AgentProfile
        self.user_profiles: Dict[int, AgentProfile] = {}
        
        # Night mode state
        self.night_mode: bool = False
    
    async def process_request(
        self,
        user_input: str,
        tz_name: str,
        metadata: Optional[Dict[str, Any]] = None,
        allowed_agents: Optional[set[str]] = None,
        perf_enabled: bool = True,
    ) -> Dict[str, Any]:
        """Process a user request through the network.
        
        This is the main entry point that coordinates all request processing.
        
        Args:
            user_input: The user's natural language request
            tz_name: Timezone name for the request
            metadata: Additional request metadata
            allowed_agents: Set of allowed agent names (None = all allowed)
            perf_enabled: Whether to track performance metrics
            
        Returns:
            Dict with response and execution details
        """
        timer = RequestTimer().start()
        
        # Extract and prepare metadata
        req_metadata = self._extract_metadata(metadata)
        
        # Setup performance tracking if enabled
        tracker = self._setup_performance_tracking(perf_enabled)
        new_tracker = tracker is not None
        
        # Apply user profile if available
        self._apply_user_profile(req_metadata)
        
        try:
            # Check night mode first
            if self.night_mode:
                result = await self._handle_night_mode(
                    user_input, req_metadata, timer
                )
                if result:
                    return result
            
            # Try protocol match (fast path)
            protocol_result = await self._try_protocol_match(
                user_input,
                req_metadata,
                allowed_agents,
                timer,
                tracker,
            )
            if protocol_result:
                return protocol_result
            
            # Fall back to NLU routing
            return await self._route_to_nlu(
                user_input,
                req_metadata,
                allowed_agents,
                timer,
                tracker,
            )
        
        finally:
            # Cleanup tracking
            if new_tracker and tracker:
                tracker.stop()
                tracker.save()
                self.logger.log("INFO", "Performance summary", tracker.summary())
    
    def _extract_metadata(
        self, metadata: Optional[Dict[str, Any]]
    ) -> RequestMetadata:
        """Extract and normalize request metadata.
        
        Args:
            metadata: Raw metadata dict from request
            
        Returns:
            RequestMetadata object with normalized values
        """
        default_user_id = int(getenv("DEFAULT_USER_ID", "1"))
        
        if not metadata:
            return RequestMetadata(user_id=default_user_id)
        
        user_id = metadata.get("user_id", default_user_id)
        if user_id is None:
            user_id = default_user_id
        
        # Extract profile if present
        profile = None
        profile_data = metadata.get("profile")
        if profile_data:
            profile = AgentProfile(**profile_data)
            self.user_profiles[user_id] = profile
        elif user_id in self.user_profiles:
            profile = self.user_profiles[user_id]
        
        return RequestMetadata(
            user_id=user_id,
            device=metadata.get("device"),
            location=metadata.get("location"),
            source=metadata.get("source"),
            profile=profile,
        )
    
    def _setup_performance_tracking(
        self, enabled: bool
    ) -> Optional[PerfTracker]:
        """Setup performance tracking if enabled.
        
        Args:
            enabled: Whether performance tracking is enabled
            
        Returns:
            PerfTracker instance or None
        """
        tracker = get_tracker()
        if tracker is None and enabled:
            tracker = PerfTracker(enabled=enabled)
            tracker.start()
            return tracker
        return None
    
    def _apply_user_profile(self, metadata: RequestMetadata) -> None:
        """Apply user profile to chat agent if available.
        
        Args:
            metadata: Request metadata with profile info
        """
        if not metadata.profile:
            return
        
        # Get chat agent from network
        chat_agent = self.network.agents.get("ChatAgent")
        if chat_agent and hasattr(chat_agent, "profile"):
            chat_agent.profile = metadata.profile
            if hasattr(chat_agent, "current_user_id"):
                chat_agent.current_user_id = metadata.user_id
    
    async def _handle_night_mode(
        self,
        user_input: str,
        metadata: RequestMetadata,
        timer: RequestTimer,
    ) -> Optional[Dict[str, Any]]:
        """Handle request during night mode (maintenance mode).
        
        Args:
            user_input: User's request
            metadata: Request metadata
            timer: Request timer
            
        Returns:
            Response dict if request should be blocked, None otherwise
        """
        # Check if it's a wake up protocol
        if self.protocol_runtime:
            match_result = self.protocol_runtime.try_match(user_input)
            if match_result and match_result["protocol"].name == "wake_up":
                return None  # Allow wake up protocol
        
        # Block other requests during night mode
        maintenance_response = "Jarvis is in maintenance mode"
        await self.response_logger.log_failed_interaction(
            user_input=user_input,
            error_message=maintenance_response,
            intent="maintenance",
            latency_ms=timer.elapsed_ms(),
            user_id=metadata.user_id,
            device=metadata.device,
            location=metadata.location,
            source=metadata.source,
        )
        return {"response": maintenance_response}
    
    async def _try_protocol_match(
        self,
        user_input: str,
        metadata: RequestMetadata,
        allowed_agents: Optional[set[str]],
        timer: RequestTimer,
        tracker: Optional[PerfTracker],
    ) -> Optional[Dict[str, Any]]:
        """Try to match and execute a protocol.
        
        Args:
            user_input: User's request
            metadata: Request metadata
            allowed_agents: Allowed agent names
            timer: Request timer
            tracker: Performance tracker
            
        Returns:
            Response dict if protocol matched and executed, None otherwise
        """
        if not self.protocol_runtime:
            return None
        
        match_result = self.protocol_runtime.try_match(user_input)
        if not match_result:
            return None
        
        protocol = match_result["protocol"]
        arguments = match_result["arguments"]
        
        self.logger.log(
            "INFO",
            "Protocol matched",
            f"Command: '{user_input}' -> Protocol: '{protocol.name}', Args: {arguments}",
        )
        
        try:
            # Execute protocol with tracking
            if tracker:
                async with tracker.timer(
                    "protocol_execution", metadata={"protocol": protocol.name}
                ):
                    response = await self.protocol_runtime.run_and_format(
                        match_result,
                        trigger_phrase=user_input,
                        metadata={
                            "user_id": metadata.user_id,
                            "device": metadata.device,
                            "location": metadata.location,
                            "source": metadata.source,
                        },
                        allowed_agents=allowed_agents,
                    )
            else:
                response = await self.protocol_runtime.run_and_format(
                    match_result,
                    trigger_phrase=user_input,
                    metadata={
                        "user_id": metadata.user_id,
                        "device": metadata.device,
                        "location": metadata.location,
                        "source": metadata.source,
                    },
                    allowed_agents=allowed_agents,
                )
            
            # Extract response text
            response_text = (
                response.get("response", str(response))
                if isinstance(response, dict)
                else str(response)
            )
            
            # Log successful execution
            await self.response_logger.log_successful_interaction(
                user_input=user_input,
                response=response_text,
                intent="protocol",
                protocol_executed=protocol.name,
                latency_ms=timer.elapsed_ms(),
                user_id=metadata.user_id,
                device=metadata.device,
                location=metadata.location,
                source=metadata.source,
            )
            
            return {
                "response": response,
                "protocol_executed": protocol.name,
                "execution_time": "fast",
            }
        
        except Exception as e:
            self.logger.log(
                "ERROR",
                f"Protocol execution failed for '{protocol.name}'",
                str(e),
            )
            
            # Log failure
            await self.response_logger.log_failed_interaction(
                user_input=user_input,
                error_message=f"Protocol execution failed: {str(e)}",
                intent="protocol",
                protocol_executed=protocol.name,
                latency_ms=timer.elapsed_ms(),
                user_id=metadata.user_id,
                device=metadata.device,
                location=metadata.location,
                source=metadata.source,
            )
            
            # Fall through to NLU routing
            return None
    
    async def _route_to_nlu(
        self,
        user_input: str,
        metadata: RequestMetadata,
        allowed_agents: Optional[set[str]],
        timer: RequestTimer,
        tracker: Optional[PerfTracker],
    ) -> Dict[str, Any]:
        """Route request to NLU agent for intent classification and execution.
        
        Args:
            user_input: User's request
            metadata: Request metadata
            allowed_agents: Allowed agent names
            timer: Request timer
            tracker: Performance tracker
            
        Returns:
            Response dict with results
        """
        request_id = str(uuid.uuid4())
        
        # Get conversation history
        conversation_history = self.conversation_history.get(metadata.user_id, [])
        
        self.logger.log(
            "DEBUG",
            f"Retrieved conversation history for user {metadata.user_id}",
            f"{len(conversation_history)} turns",
        )
        
        # Request NLU processing
        await self.network.request_capability(
            from_agent="JarvisSystem",
            capability="intent_matching",
            data={
                "input": user_input,
                "conversation_history": conversation_history,
            },
            request_id=request_id,
            allowed_agents=allowed_agents,
        )
        
        try:
            # Wait for NLU response
            if tracker:
                async with tracker.timer("nlu_routing"):
                    result = await self.network.wait_for_response(
                        request_id, timeout=self.response_timeout
                    )
            else:
                result = await self.network.wait_for_response(
                    request_id, timeout=self.response_timeout
                )
            
            # Extract response and metadata
            response_text = self._extract_response_text(result)
            intent, capability, agent_results, tool_calls = self._extract_response_metadata(result)
            
            # Store conversation history
            if response_text:
                self._store_conversation_turn(
                    metadata.user_id, user_input, response_text
                )
            
            # Log successful interaction
            await self.response_logger.log_successful_interaction(
                user_input=user_input,
                response=response_text or "",
                intent=intent,
                capability=capability,
                agent_results=agent_results,
                tool_calls=tool_calls,
                latency_ms=timer.elapsed_ms(),
                user_id=metadata.user_id,
                device=metadata.device,
                location=metadata.location,
                source=metadata.source,
            )
            
            return {"response": response_text} if response_text else result
        
        except asyncio.TimeoutError:
            self.logger.log(
                "ERROR",
                "NLU routing timed out",
                f"request_id={request_id}",
            )
            
            error_response = "The request took too long to complete. Please try again."
            await self.response_logger.log_failed_interaction(
                user_input=user_input,
                error_message=error_response,
                intent="timeout",
                latency_ms=timer.elapsed_ms(),
                user_id=metadata.user_id,
                device=metadata.device,
                location=metadata.location,
                source=metadata.source,
            )
            
            return {"response": error_response}
        
        except Exception as e:
            self.logger.log("ERROR", "Error in NLU routing", str(e))
            
            error_response = f"Sorry, I encountered an error: {str(e)}"
            await self.response_logger.log_failed_interaction(
                user_input=user_input,
                error_message=error_response,
                intent="error",
                latency_ms=timer.elapsed_ms(),
                user_id=metadata.user_id,
                device=metadata.device,
                location=metadata.location,
                source=metadata.source,
            )
            
            return {"response": error_response}
    
    def _extract_response_text(self, result: Any) -> Optional[str]:
        """Extract response text from standardized agent result.
        
        Args:
            result: Result from agent (should be standardized AgentResponse format)
            
        Returns:
            Response text string or None
        """
        if isinstance(result, dict) and "response" in result:
            # Standard format: result["response"] contains the text
            return result["response"]
        elif isinstance(result, dict):
            return str(result)
        else:
            return str(result)
    
    def _extract_response_metadata(
        self, result: Any
    ) -> tuple[Optional[str], Optional[str], Optional[Any], Optional[Any]]:
        """Extract metadata from agent result.
        
        Args:
            result: Result from agent (standardized AgentResponse format)
            
        Returns:
            Tuple of (intent, capability, agent_results, tool_calls)
        """
        if not isinstance(result, dict):
            return "chat", None, None, None
        
        # Standard format uses "metadata" field for extra info
        metadata = result.get("metadata", {})
        
        intent = metadata.get("intent", result.get("intent", "chat"))
        capability = metadata.get("capability", result.get("capability"))
        
        # Actions in standard format
        actions = result.get("actions", [])
        
        # Check for nested results (legacy support)
        agent_results = result.get("results")
        tool_calls = result.get("tool_calls")
        
        # Extract from actions if not found
        if not capability and actions:
            if isinstance(actions, list) and actions:
                first_action = actions[0]
                if isinstance(first_action, dict):
                    capability = first_action.get("function")
        
        return intent, capability, agent_results, tool_calls
    
    def _store_conversation_turn(
        self, user_id: int, user_input: str, response: str
    ) -> None:
        """Store a conversation turn in history.
        
        Args:
            user_id: User ID
            user_input: User's input
            response: System's response
        """
        if user_id not in self.conversation_history:
            self.conversation_history[user_id] = []
        
        history = self.conversation_history[user_id]
        history.append({"user": user_input, "assistant": response})
        
        # Keep only last N turns
        if len(history) > self.max_history_length:
            self.conversation_history[user_id] = history[-self.max_history_length:]
        
        self.logger.log(
            "DEBUG",
            f"Stored conversation turn for user {user_id}",
            f"History now has {len(self.conversation_history[user_id])} turns",
        )

