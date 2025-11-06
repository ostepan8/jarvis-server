"""
Simple example showing how to test agent routing flows.

Run with: python tests/example_routing_test.py
"""

import asyncio
from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.nlu_agent import NLUAgent
from jarvis.agents.base import NetworkAgent
from tests.tools.routing_tracker import RoutingTracker, wrap_network_with_tracker


class SimpleLightsAgent(NetworkAgent):
    """Simple lights agent for example."""

    @property
    def capabilities(self):
        return {"control_lights"}

    async def _handle_capability_request(self, message):
        result = {"status": "lights_on", "capability": "control_lights"}
        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )


async def example_test():
    """Example test showing routing flow."""
    print("\n" + "=" * 70)
    print("EXAMPLE: Testing NLU → Lights → NLU routing")
    print("=" * 70 + "\n")

    # Create tracker
    tracker = RoutingTracker()

    # Create network and wrap with tracker
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # Create agents (using mock AI client)
    from jarvis.ai_clients.base import BaseAIClient

    class MockAI(BaseAIClient):
        call_count = 0
        responses = [
            '{"intent": "perform_capability", "capability": "control_lights"}',
            "The lights have been turned on successfully.",
        ]

        async def weak_chat(self, messages, tools=None):
            response = self.responses[self.call_count % len(self.responses)]
            self.call_count += 1
            return type("Msg", (), {"content": response}), None

        async def strong_chat(self, messages, tools=None):
            return await self.weak_chat(messages, tools)

    ai_client = MockAI()

    nlu = NLUAgent(ai_client)
    lights = SimpleLightsAgent()

    network.register_agent(nlu)
    network.register_agent(lights)
    await network.start()

    try:
        # Make request
        request_id = "example_001"
        await network.request_capability(
            from_agent="ExampleSystem",
            capability="intent_matching",
            data={"input": "Turn on the lights"},
            request_id=request_id,
        )

        # Wait a bit for routing
        await asyncio.sleep(0.5)

        # Show the flow
        print("\nROUTING FLOW:")
        print(tracker.format_flow_diagram(request_id))

        # Show participants
        participants = tracker.get_agent_participants(request_id)
        print(f"\nAgents involved: {', '.join(participants)}")

        # Get flow as list
        flow = tracker.get_flow(request_id)
        print(f"\nFlow steps ({len(flow)} total):")
        for i, step in enumerate(flow, 1):
            print(f"  {i}. {step}")

        print("\n" + "=" * 70)
        print("✅ Test complete!")
        print("=" * 70 + "\n")

    finally:
        await network.stop()


if __name__ == "__main__":
    asyncio.run(example_test())
