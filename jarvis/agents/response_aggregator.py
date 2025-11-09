# agents/response_aggregator.py

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

from ..logging import JarvisLogger
from .message import Message
from .response import AgentResponse, merge_responses


class AggregationStrategy(Enum):
    """Strategy for aggregating multiple responses."""

    FIRST = "first"  # Return first response received
    ALL = "all"  # Wait for all responses
    MAJORITY = "majority"  # Wait for majority of responses
    TIMEOUT = "timeout"  # Return all responses received within timeout


@dataclass
class ResponseTracker:
    """Tracks responses for a capability request."""

    request_id: str
    capability: str
    expected_providers: List[str]
    strategy: AggregationStrategy
    timeout: float
    created_at: float = field(default_factory=time.time)
    responses: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    received_from: Set[str] = field(default_factory=set)
    future: Optional[asyncio.Future] = None

    def is_complete(self) -> bool:
        """Check if aggregation is complete based on strategy."""
        if self.strategy == AggregationStrategy.FIRST:
            return len(self.responses) > 0 or len(self.errors) > 0
        elif self.strategy == AggregationStrategy.ALL:
            return len(self.received_from) >= len(self.expected_providers)
        elif self.strategy == AggregationStrategy.MAJORITY:
            required = (len(self.expected_providers) // 2) + 1
            return len(self.received_from) >= required
        elif self.strategy == AggregationStrategy.TIMEOUT:
            return time.time() - self.created_at >= self.timeout
        return False

    def get_result(self) -> Dict[str, Any]:
        """Get aggregated result in standardized format."""
        # Handle failure case
        if self.errors and not self.responses:
            from .response import AgentResponse, ErrorInfo
            return AgentResponse.error_response(
                response="All providers failed to respond",
                error=ErrorInfo(
                    message="All providers failed",
                    details={"errors": self.errors}
                )
            ).to_dict()

        # Handle empty response case
        if not self.responses:
            from .response import AgentResponse, ErrorInfo
            return AgentResponse.error_response(
                response="No responses received",
                error=ErrorInfo(message="No responses")
            ).to_dict()

        # For FIRST strategy, return the first response
        if self.strategy == AggregationStrategy.FIRST:
            return self.responses[0].get("content", {})
        
        # For other strategies, merge multiple responses
        elif self.strategy in (
            AggregationStrategy.ALL,
            AggregationStrategy.MAJORITY,
            AggregationStrategy.TIMEOUT,
        ):
            # Try to merge standardized responses
            agent_responses = []
            for resp_data in self.responses:
                content = resp_data.get("content", {})
                if isinstance(content, dict) and "success" in content:
                    agent_responses.append(AgentResponse.from_dict(content))
            
            if agent_responses:
                merged = merge_responses(agent_responses)
                result = merged.to_dict()
                result["metadata"] = result.get("metadata", {})
                result["metadata"].update({
                    "received_from": list(self.received_from),
                    "expected_from": self.expected_providers,
                })
                return result
            
            # Fallback for non-standard responses
            return {
                "success": True,
                "response": "Multiple responses received",
                "data": {
                    "responses": self.responses,
                    "received_from": list(self.received_from),
                    "expected_from": self.expected_providers,
                },
            }
        
        from .response import AgentResponse, ErrorInfo
        return AgentResponse.error_response(
            response="Unknown aggregation strategy",
            error=ErrorInfo(message="Unknown strategy")
        ).to_dict()


class ResponseAggregator:
    """Centralized response aggregation service for agent network."""

    def __init__(
        self,
        logger: Optional[JarvisLogger] = None,
        default_timeout: float = 30.0,
        cleanup_interval: float = 60.0,
    ) -> None:
        self.logger = logger or JarvisLogger()
        self.default_timeout = default_timeout
        self.cleanup_interval = cleanup_interval
        self._trackers: Dict[str, ResponseTracker] = {}
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the aggregator and cleanup task."""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.logger.log("INFO", "ResponseAggregator started")

    async def stop(self) -> None:
        """Stop the aggregator."""
        self._running = False
        if self._cleanup_task:
            await self._cleanup_task
        self.logger.log("INFO", "ResponseAggregator stopped")

    def register_request(
        self,
        request_id: str,
        capability: str,
        expected_providers: List[str],
        strategy: AggregationStrategy = AggregationStrategy.FIRST,
        timeout: Optional[float] = None,
    ) -> asyncio.Future:
        """
        Register a new request for response aggregation.

        Returns a Future that will be fulfilled when aggregation is complete.
        """
        if timeout is None:
            timeout = self.default_timeout

        loop = asyncio.get_event_loop()
        fut = loop.create_future()

        tracker = ResponseTracker(
            request_id=request_id,
            capability=capability,
            expected_providers=expected_providers,
            strategy=strategy,
            timeout=timeout,
            future=fut,
        )

        self._trackers[request_id] = tracker

        # Start timeout task
        asyncio.create_task(self._handle_timeout(request_id, timeout))

        self.logger.log(
            "DEBUG",
            f"Registered request {request_id}",
            f"Capability: {capability}, Providers: {len(expected_providers)}, Strategy: {strategy.value}",
        )

        return fut

    def add_response(
        self,
        request_id: str,
        from_agent: str,
        content: Any,
        is_error: bool = False,
    ) -> bool:
        """
        Add a response to a tracked request.

        Returns True if the response was added, False if request not found.
        """
        tracker = self._trackers.get(request_id)
        if not tracker:
            return False

        tracker.received_from.add(from_agent)

        response_data = {
            "from_agent": from_agent,
            "content": content,
            "timestamp": time.time(),
        }

        if is_error:
            tracker.errors.append(response_data)
        else:
            tracker.responses.append(response_data)

        # Check if aggregation is complete
        if tracker.is_complete() and tracker.future and not tracker.future.done():
            result = tracker.get_result()
            tracker.future.set_result(result)
            self.logger.log(
                "DEBUG",
                f"Aggregation complete for {request_id}",
                f"Responses: {len(tracker.responses)}, Errors: {len(tracker.errors)}",
            )

        return True

    async def _handle_timeout(self, request_id: str, timeout: float) -> None:
        """Handle timeout for a request."""
        await asyncio.sleep(timeout)

        tracker = self._trackers.get(request_id)
        if tracker and tracker.future and not tracker.future.done():
            # Timeout reached, fulfill with whatever we have
            result = tracker.get_result()
            tracker.future.set_result(result)
            self.logger.log(
                "DEBUG",
                f"Request {request_id} timed out",
                f"Received {len(tracker.responses)} responses from {len(tracker.received_from)} providers",
            )

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup of completed trackers."""
        while self._running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                await self._cleanup_completed()
            except Exception as exc:
                self.logger.log("ERROR", "ResponseAggregator cleanup error", str(exc))

    async def _cleanup_completed(self) -> None:
        """Remove completed trackers."""
        current_time = time.time()
        to_remove = []

        for request_id, tracker in self._trackers.items():
            # Remove if completed or expired
            if tracker.future and tracker.future.done():
                to_remove.append(request_id)
            elif current_time - tracker.created_at > tracker.timeout * 2:
                # Expired (2x timeout for safety)
                to_remove.append(request_id)

        for request_id in to_remove:
            del self._trackers[request_id]

        if to_remove:
            self.logger.log(
                "DEBUG",
                f"Cleaned up {len(to_remove)} completed trackers",
                "",
            )

    def get_tracker(self, request_id: str) -> Optional[ResponseTracker]:
        """Get tracker for a request ID."""
        return self._trackers.get(request_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregator statistics."""
        return {
            "active_trackers": len(self._trackers),
            "completed_trackers": sum(
                1 for t in self._trackers.values() if t.future and t.future.done()
            ),
        }
