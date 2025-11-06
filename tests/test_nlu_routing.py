"""
Integration tests for NLU-based routing in the decentralized network.

These tests verify that:
1. NLU routes to correct agents
2. Agents can communicate with each other
3. Multi-step workflows work correctly
4. Routing paths are tracked and verifiable
"""

import asyncio
import pytest
import os
from unittest.mock import AsyncMock, patch

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.nlu_agent import NLUAgent
from jarvis.agents.base import NetworkAgent
from jarvis.ai_clients.base import BaseAIClient
from jarvis.logging import JarvisLogger
from tests.tools.routing_tracker import RoutingTracker, wrap_network_with_tracker


# Check if we should use real LLMs (set USE_REAL_LLM=1 to enable)
USE_REAL_LLM = os.getenv("USE_REAL_LLM", "0") == "1"


class MockAIClient(BaseAIClient):
    """Mock AI client that returns predictable responses."""

    def __init__(self, responses: dict):
        """
        Args:
            responses: Dict mapping response type to content
                e.g., {"intent_matching": {...}, "response_formatting": "..."}
        """
        self.responses = responses
        self.call_history = []

    async def strong_chat(self, messages, tools=None):
        self.call_history.append(("strong_chat", messages))
        content = self.responses.get("strong_chat", "")
        return (type("Msg", (), {"content": content}), None)

    async def weak_chat(self, messages, tools=None):
        self.call_history.append(("weak_chat", messages))
        # Try to determine what type of call this is
        sys_msg = messages[0].get("content", "") if messages else ""

        if (
            "intent_matching" in sys_msg.lower()
            or "Natural Language Understanding" in sys_msg
        ):
            response = self.responses.get("intent_matching", {})
            if isinstance(response, dict):
                import json

                response = json.dumps(response)
            content = response
        elif "format" in sys_msg.lower() or "response" in sys_msg.lower():
            content = self.responses.get(
                "response_formatting", "Task completed successfully."
            )
        elif "extract" in sys_msg.lower() or "capabilities" in sys_msg.lower():
            response = self.responses.get("extract_capabilities", [])
            if isinstance(response, list):
                import json

                content = json.dumps({"capabilities": response})
            else:
                content = response
        else:
            content = self.responses.get("weak_chat", "")

        return (type("Msg", (), {"content": content}), None)


class MockLightsAgent(NetworkAgent):
    """Mock lighting agent for testing."""

    def __init__(self, response_with_followup: bool = False):
        super().__init__("LightingAgent")
        self.response_with_followup = response_with_followup

    @property
    def capabilities(self):
        return {"control_lights"}

    async def _handle_capability_request(self, message):
        """Handle capability request and optionally request follow-up."""
        result = {
            "status": "success",
            "action": "lights_turned_on",
            "capability": "control_lights",
        }

        # Optionally indicate that more work is needed
        if self.response_with_followup:
            result["needs_followup"] = True
            result["followup_capability"] = "get_today_schedule"
            result["followup_prompt"] = "What do I have today?"

        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message):
        pass


class MockCalendarAgent(NetworkAgent):
    """Mock calendar agent for testing."""

    def __init__(self):
        super().__init__("CollaborativeCalendarAgent")

    @property
    def capabilities(self):
        return {"get_today_schedule"}

    async def _handle_capability_request(self, message):
        result = {
            "status": "success",
            "schedule": [{"time": "10:00", "title": "Meeting"}],
            "capability": "get_today_schedule",
        }
        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message):
        pass


@pytest.mark.asyncio
async def test_simple_nlu_to_agent_routing():
    """Test that NLU routes a simple request to the correct agent."""
    tracker = RoutingTracker()

    # Setup network with tracking
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # Create AI client with mock response
    ai_client = MockAIClient(
        {
            "intent_matching": {
                "intent": "perform_capability",
                "capability": "control_lights",
            }
        }
    )

    # Create agents
    nlu = NLUAgent(ai_client, logger=JarvisLogger())
    lights = MockLightsAgent()

    network.register_agent(nlu)
    network.register_agent(lights)
    await network.start()

    try:
        # Send request to NLU
        request_id = "test_simple_001"
        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Turn on the lights"},
            request_id=request_id,
        )

        # Wait for response
        import asyncio

        await asyncio.sleep(0.5)  # Give time for routing

        # Verify routing path
        flow = tracker.get_flow(request_id)
        print(f"\nRouting flow: {flow}")
        print(tracker.format_flow_diagram(request_id))

        # Expected: NLU → Lights → NLU → TestSystem
        assert len(flow) >= 3, f"Expected at least 3 routing steps, got {len(flow)}"
        assert any(
            "NLUAgent" in step and "control_lights" in step for step in flow
        ), "NLU should have routed to control_lights"
        assert any(
            "LightingAgent" in step and "response" in step for step in flow
        ), "LightingAgent should have responded"

        # Verify agents participated
        participants = tracker.get_agent_participants(request_id)
        assert "NLUAgent" in participants
        assert "LightingAgent" in participants

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_multi_step_routing():
    """Test that NLU handles multi-step workflows correctly."""
    tracker = RoutingTracker()

    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    ai_client = MockAIClient(
        {
            "intent_matching": {"intent": None},  # Triggers multi-step extraction
            "extract_capabilities": ["control_lights", "get_today_schedule"],
            "response_formatting": "Lights are on and you have a meeting at 10:00.",
        }
    )

    nlu = NLUAgent(ai_client, logger=JarvisLogger())
    lights = MockLightsAgent()
    calendar = MockCalendarAgent()

    network.register_agent(nlu)
    network.register_agent(lights)
    network.register_agent(calendar)
    await network.start()

    try:
        request_id = "test_multistep_001"
        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Turn on lights and tell me my schedule"},
            request_id=request_id,
        )

        await asyncio.sleep(1.0)  # Give time for multi-step routing

        flow = tracker.get_flow(request_id)
        print(f"\nMulti-step routing flow:")
        print(tracker.format_flow_diagram(request_id))

        # Should route to both capabilities
        assert any("control_lights" in step for step in flow)
        assert any("get_today_schedule" in step for step in flow)

        participants = tracker.get_agent_participants(request_id)
        assert "LightingAgent" in participants
        assert "CollaborativeCalendarAgent" in participants

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_agent_initiated_followup():
    """Test that agents can request follow-ups through NLU."""
    tracker = RoutingTracker()

    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    ai_client = MockAIClient(
        {
            "intent_matching": {
                "intent": "perform_capability",
                "capability": "control_lights",
            },
            "response_formatting": "Lights are on. You have a meeting at 10:00.",
        }
    )

    nlu = NLUAgent(ai_client, logger=JarvisLogger())
    lights = MockLightsAgent(response_with_followup=True)  # Will request follow-up
    calendar = MockCalendarAgent()

    network.register_agent(nlu)
    network.register_agent(lights)
    network.register_agent(calendar)
    await network.start()

    try:
        request_id = "test_followup_001"
        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Turn on lights and check my calendar"},
            request_id=request_id,
        )

        await asyncio.sleep(1.0)

        flow = tracker.get_flow(request_id)
        print(f"\nAgent-initiated follow-up flow:")
        print(tracker.format_flow_diagram(request_id))

        # Should have gone: NLU → Lights → NLU → Calendar → NLU → TestSystem
        assert any("control_lights" in step for step in flow)
        assert any("get_today_schedule" in step for step in flow)

        # Verify all agents participated
        participants = tracker.get_agent_participants(request_id)
        assert "LightingAgent" in participants
        assert "CollaborativeCalendarAgent" in participants

    finally:
        await network.stop()


@pytest.mark.asyncio
@pytest.mark.skipif(not USE_REAL_LLM, reason="Set USE_REAL_LLM=1 to run with real LLM")
async def test_real_llm_routing():
    """Integration test with real LLM (requires API keys)."""
    from jarvis.ai_clients.factory import AIClientFactory
    import os

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY not set")

    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    ai_client = AIClientFactory.create("openai", api_key=api_key)

    nlu = NLUAgent(ai_client, logger=JarvisLogger())
    lights = MockLightsAgent()

    network.register_agent(nlu)
    network.register_agent(lights)
    await network.start()

    try:
        request_id = "test_reallm_001"

        # Request to NLU
        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Turn on the lights please"},
            request_id=request_id,
        )

        # Wait for response
        result = await network.wait_for_response(request_id, timeout=30.0)

        # Print full flow
        print("\n" + "=" * 60)
        print("REAL LLM TEST RESULTS")
        print("=" * 60)
        print(tracker.format_flow_diagram(request_id))
        print(f"\nFinal result: {result}")
        print("=" * 60)

        # Verify we got a response
        assert result is not None

        # Verify routing happened
        flow = tracker.get_flow(request_id)
        assert len(flow) > 0, "Should have routing events"

        # Verify NLU and Lights participated
        participants = tracker.get_agent_participants(request_id)
        assert "NLUAgent" in participants

    finally:
        await network.stop()


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_nlu_routing.py -v -s
    # Or with real LLM: USE_REAL_LLM=1 python -m pytest tests/test_nlu_routing.py::test_real_llm_routing -v -s
    pytest.main([__file__, "-v", "-s"])
