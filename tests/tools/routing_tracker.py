"""
Test utilities for tracking agent-to-agent routing flows.
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict

from jarvis.agents.message import Message


@dataclass
class RoutingEvent:
    """A single routing event in the flow."""

    timestamp: datetime
    from_agent: str
    to_agent: Optional[str]  # None = broadcast
    message_type: str
    capability: Optional[str] = None
    request_id: str = ""

    def __str__(self) -> str:
        target = to_agent or "ALL"
        if self.message_type == "capability_request":
            return f"{self.from_agent} → {target} [{self.capability}]"
        elif self.message_type == "capability_response":
            return f"{self.from_agent} → {target} [response]"
        return f"{self.from_agent} → {target} [{self.message_type}]"


class RoutingTracker:
    """
    Tracks agent-to-agent message flow for testing.

    Example:
        tracker = RoutingTracker()
        network = wrap_network_with_tracker(network, tracker)

        # ... run test ...

        flow = tracker.get_flow("request_id")
        assert flow == ["NLUAgent → ALL [control_lights]", "LightingAgent → NLUAgent [response]"]
    """

    def __init__(self):
        self.events: List[RoutingEvent] = []
        self.events_by_request: Dict[str, List[RoutingEvent]] = defaultdict(list)
        self.capability_requests: Dict[str, List[RoutingEvent]] = defaultdict(list)
        self._enabled = True

    def track_message(self, message: Message) -> None:
        """Track a message flow."""
        if not self._enabled:
            return

        event = RoutingEvent(
            timestamp=datetime.now(),
            from_agent=message.from_agent,
            to_agent=message.to_agent,
            message_type=message.message_type,
            capability=(
                message.content.get("capability")
                if isinstance(message.content, dict)
                else None
            ),
            request_id=message.request_id,
        )

        self.events.append(event)

        if message.request_id:
            self.events_by_request[message.request_id].append(event)

        if event.message_type == "capability_request" and event.capability:
            self.capability_requests[event.capability].append(event)

    def get_flow(self, request_id: str) -> List[str]:
        """Get the routing flow as a list of string descriptions."""
        return [str(event) for event in self.events_by_request.get(request_id, [])]

    def get_flow_verbose(self, request_id: str) -> List[RoutingEvent]:
        """Get the routing flow as event objects."""
        return self.events_by_request.get(request_id, [])

    def get_all_flows(self) -> Dict[str, List[str]]:
        """Get all flows indexed by request_id."""
        return {
            req_id: self.get_flow(req_id) for req_id in self.events_by_request.keys()
        }

    def get_agent_participants(self, request_id: str) -> List[str]:
        """Get list of agents that participated in a request."""
        events = self.events_by_request.get(request_id, [])
        agents = set()
        for event in events:
            agents.add(event.from_agent)
            if event.to_agent:
                agents.add(event.to_agent)
        return sorted(list(agents))

    def get_capability_usage(self, capability: str) -> List[RoutingEvent]:
        """Get all events for a specific capability."""
        return self.capability_requests.get(capability, [])

    def assert_path(self, request_id: str, expected_path: List[str]) -> bool:
        """
        Assert that a request followed the expected path.

        Args:
            request_id: The request ID to check
            expected_path: List of expected routing steps, e.g.:
                ["NLUAgent → ALL [control_lights]", "LightingAgent → NLUAgent [response]"]

        Returns:
            True if path matches, False otherwise
        """
        actual_path = self.get_flow(request_id)

        # Match if actual path contains all expected steps in order
        if len(actual_path) < len(expected_path):
            return False

        expected_idx = 0
        for actual_step in actual_path:
            if expected_idx < len(expected_path):
                expected_step = expected_path[expected_idx]
                # Flexible matching: check if actual step contains expected elements
                if self._step_matches(actual_step, expected_step):
                    expected_idx += 1

        return expected_idx == len(expected_path)

    def _step_matches(self, actual: str, expected: str) -> bool:
        """Check if an actual routing step matches an expected pattern."""
        # Simple substring matching - can be enhanced
        # Expected can be partial, e.g., "NLUAgent" or "→ ALL [control_lights]"
        return expected in actual or actual in expected

    def format_flow_diagram(self, request_id: str) -> str:
        """Format the flow as a readable diagram."""
        events = self.events_by_request.get(request_id, [])
        if not events:
            return f"No events found for request_id: {request_id}"

        lines = [f"\nFlow for request_id: {request_id}"]
        lines.append("=" * 60)

        for i, event in enumerate(events, 1):
            arrow = "→"
            target = event.to_agent or "ALL"
            lines.append(f"{i}. {event.from_agent} {arrow} {target}")
            if event.capability:
                lines.append(f"   Capability: {event.capability}")
            if event.message_type == "capability_response":
                lines.append(f"   Type: response")

        lines.append("=" * 60)
        return "\n".join(lines)

    def reset(self) -> None:
        """Clear all tracked events."""
        self.events.clear()
        self.events_by_request.clear()
        self.capability_requests.clear()

    def disable(self) -> None:
        """Disable tracking."""
        self._enabled = False

    def enable(self) -> None:
        """Enable tracking."""
        self._enabled = True


def wrap_network_with_tracker(network, tracker: RoutingTracker):
    """
    Wrap an AgentNetwork to automatically track all messages.

    This monkey-patches the network's message queue to track messages.
    """
    original_put = network.message_queue.put

    async def tracked_put(message: Message) -> None:
        tracker.track_message(message)
        return await original_put(message)

    network.message_queue.put = tracked_put
    return network
