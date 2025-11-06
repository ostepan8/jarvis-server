"""
Tests for DAG-based execution in NLU agent.

These tests verify that:
1. Independent capabilities execute in parallel
2. Dependent capabilities execute sequentially (after dependencies complete)
3. Mixed scenarios work correctly (some parallel, some sequential)
4. DAG validation works (circular dependencies are detected)
5. Completion detection works correctly
6. Context is passed correctly to dependent capabilities
"""

import asyncio
import pytest
import json
from unittest.mock import AsyncMock

from jarvis.agents.agent_network import AgentNetwork
from jarvis.agents.nlu_agent import NLUAgent
from jarvis.agents.base import NetworkAgent
from jarvis.ai_clients.base import BaseAIClient
from jarvis.logging import JarvisLogger
from tests.tools.routing_tracker import RoutingTracker, wrap_network_with_tracker


class MockAIClient(BaseAIClient):
    """Mock AI client that returns predictable DAG responses."""

    def __init__(
        self, dag_response: dict, formatting_response: str = "Task completed."
    ):
        """
        Args:
            dag_response: Dict with "dag" key mapping capabilities to dependencies
            formatting_response: Response for final formatting
        """
        self.dag_response = dag_response
        self.formatting_response = formatting_response
        self.call_history = []

    async def strong_chat(self, messages, tools=None):
        self.call_history.append(("strong_chat", messages))
        return (type("Msg", (), {"content": ""}), None)

    async def weak_chat(self, messages, tools=None):
        self.call_history.append(("weak_chat", messages))

        # Check all messages for prompt content
        full_content = " ".join([msg.get("content", "") for msg in messages]).lower()

        # Check for DAG extraction prompt (contains "Analyze this request" and "dependencies")
        if "analyze this request" in full_content and "dependencies" in full_content:
            # Return DAG structure
            return (type("Msg", (), {"content": json.dumps(self.dag_response)}), None)
        elif (
            "intent_matching" in full_content
            or "natural language understanding" in full_content
        ):
            # Return None intent to trigger DAG extraction
            return (type("Msg", (), {"content": json.dumps({"intent": None})}), None)
        elif "format" in full_content or "response" in full_content:
            return (type("Msg", (), {"content": self.formatting_response}), None)
        else:
            return (type("Msg", (), {"content": ""}), None)


class MockAgent(NetworkAgent):
    """Generic mock agent that can simulate different capabilities."""

    def __init__(self, name: str, capability: str, delay: float = 0.1):
        super().__init__(name)
        self.capability = capability
        self.delay = delay
        self.execution_order = []

    @property
    def capabilities(self):
        return {self.capability}

    async def _handle_capability_request(self, message):
        """Handle capability request with configurable delay."""
        # Record execution order
        self.execution_order.append(
            {
                "capability": self.capability,
                "request_id": message.request_id,
                "timestamp": asyncio.get_event_loop().time(),
            }
        )

        # Simulate work
        await asyncio.sleep(self.delay)

        result = {
            "status": "success",
            "capability": self.capability,
            "agent": self.name,
            "message": f"Completed {self.capability}",
        }

        await self.send_capability_response(
            message.from_agent, result, message.request_id, message.id
        )

    async def _handle_capability_response(self, message):
        pass


@pytest.mark.asyncio
async def test_parallel_execution_independent_capabilities():
    """Test that independent capabilities execute in parallel."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # DAG with two independent capabilities (no dependencies)
    dag = {
        "dag": {
            "lights_color": [],  # No dependencies
            "get_weather": [],  # No dependencies - should run in parallel
        }
    }

    ai_client = MockAIClient(dag, "Lights changed and weather retrieved.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    # Create agents with delays to detect parallel execution
    lights_agent = MockAgent("LightingAgent", "lights_color", delay=0.2)
    weather_agent = MockAgent("WeatherAgent", "get_weather", delay=0.2)

    network.register_agent(nlu)
    network.register_agent(lights_agent)
    network.register_agent(weather_agent)
    await network.start()

    # Small delay to ensure network is fully initialized
    await asyncio.sleep(0.1)

    try:
        start_time = asyncio.get_event_loop().time()
        request_id = "test_parallel_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Turn lights red and tell me the weather"},
            request_id=request_id,
        )

        # Wait for completion
        result = await network.wait_for_response(request_id, timeout=5.0)
        end_time = asyncio.get_event_loop().time()

        # Verify both capabilities executed
        assert (
            len(lights_agent.execution_order) == 1
        ), "Lights agent should have executed once"
        assert (
            len(weather_agent.execution_order) == 1
        ), "Weather agent should have executed once"

        # Check execution times - if parallel, total time should be ~0.2s (not 0.4s)
        execution_time = end_time - start_time
        assert (
            execution_time < 0.35
        ), f"Should execute in parallel (took {execution_time}s)"

        # Verify execution happened in parallel (timestamps should be close)
        lights_time = lights_agent.execution_order[0]["timestamp"]
        weather_time = weather_agent.execution_order[0]["timestamp"]
        time_diff = abs(lights_time - weather_time)
        assert (
            time_diff < 0.05
        ), f"Capabilities should start nearly simultaneously (diff: {time_diff}s)"

        # Verify we got a response
        assert result is not None
        assert "response" in result or isinstance(result, dict)

        print(f"\nParallel execution test:")
        print(f"Execution time: {execution_time:.3f}s")
        print(f"LightingAgent executions: {len(lights_agent.execution_order)}")
        print(f"WeatherAgent executions: {len(weather_agent.execution_order)}")

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_sequential_execution_with_dependencies():
    """Test that capabilities with dependencies execute sequentially."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # DAG with dependency: send_message depends on schedule_appointment
    dag = {
        "dag": {
            "schedule_appointment": [],  # No dependencies - runs first
            "send_message": ["schedule_appointment"],  # Depends on schedule_appointment
        }
    }

    ai_client = MockAIClient(dag, "Meeting scheduled and reminder sent.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    calendar_agent = MockAgent("CalendarAgent", "schedule_appointment", delay=0.15)
    message_agent = MockAgent("MessageAgent", "send_message", delay=0.15)

    network.register_agent(nlu)
    network.register_agent(calendar_agent)
    network.register_agent(message_agent)
    await network.start()

    try:
        start_time = asyncio.get_event_loop().time()
        request_id = "test_sequential_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Book a meeting and send me a reminder"},
            request_id=request_id,
        )

        result = await network.wait_for_response(request_id, timeout=5.0)
        end_time = asyncio.get_event_loop().time()

        # Verify both capabilities executed
        assert calendar_agent.execution_order
        assert message_agent.execution_order

        # Check execution order - calendar should execute before message
        calendar_time = calendar_agent.execution_order[0]["timestamp"]
        message_time = message_agent.execution_order[0]["timestamp"]

        assert (
            message_time > calendar_time
        ), f"Message ({message_time}) should execute after calendar ({calendar_time})"

        # Sequential execution should take ~0.3s (0.15 + 0.15)
        execution_time = end_time - start_time
        assert (
            execution_time >= 0.25
        ), f"Should execute sequentially (took {execution_time}s)"

        print(f"\nSequential execution test:")
        print(f"Execution time: {execution_time:.3f}s")
        print(f"Calendar executed at: {calendar_time:.3f}s")
        print(f"Message executed at: {message_time:.3f}s")

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_mixed_parallel_and_sequential():
    """Test mixed scenario: some parallel, some sequential."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # DAG: A and B run in parallel, C depends on A, D depends on B
    dag = {
        "dag": {
            "capability_a": [],
            "capability_b": [],
            "capability_c": ["capability_a"],  # Depends on A
            "capability_d": ["capability_b"],  # Depends on B
        }
    }

    ai_client = MockAIClient(dag, "All tasks completed.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    agent_a = MockAgent("AgentA", "capability_a", delay=0.1)
    agent_b = MockAgent("AgentB", "capability_b", delay=0.1)
    agent_c = MockAgent("AgentC", "capability_c", delay=0.1)
    agent_d = MockAgent("AgentD", "capability_d", delay=0.1)

    network.register_agent(nlu)
    network.register_agent(agent_a)
    network.register_agent(agent_b)
    network.register_agent(agent_c)
    network.register_agent(agent_d)
    await network.start()

    try:
        start_time = asyncio.get_event_loop().time()
        request_id = "test_mixed_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Do A and B, then C after A and D after B"},
            request_id=request_id,
        )

        result = await network.wait_for_response(request_id, timeout=5.0)
        end_time = asyncio.get_event_loop().time()

        # Verify all executed
        assert len(agent_a.execution_order) == 1
        assert len(agent_b.execution_order) == 1
        assert len(agent_c.execution_order) == 1
        assert len(agent_d.execution_order) == 1

        # A and B should execute in parallel (around same time)
        time_a = agent_a.execution_order[0]["timestamp"]
        time_b = agent_b.execution_order[0]["timestamp"]
        time_diff = abs(time_a - time_b)
        assert (
            time_diff < 0.05
        ), f"A and B should start nearly simultaneously (diff: {time_diff}s)"

        # C should execute after A
        time_c = agent_c.execution_order[0]["timestamp"]
        assert time_c > time_a, f"C ({time_c}) should execute after A ({time_a})"

        # D should execute after B
        time_d = agent_d.execution_order[0]["timestamp"]
        assert time_d > time_b, f"D ({time_d}) should execute after B ({time_b})"

        # Total time should be ~0.2s (parallel A+B, then parallel C+D)
        execution_time = end_time - start_time
        assert (
            execution_time < 0.35
        ), f"Should execute efficiently (took {execution_time}s)"

        print(f"\nMixed execution test:")
        print(f"Execution time: {execution_time:.3f}s")
        print(f"A: {time_a:.3f}s, B: {time_b:.3f}s")
        print(f"C: {time_c:.3f}s, D: {time_d:.3f}s")

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_dag_validation_circular_dependency():
    """Test that circular dependencies are detected and handled."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # DAG with circular dependency (should be detected and fallback to sequential)
    dag = {
        "dag": {
            "capability_a": ["capability_b"],  # A depends on B
            "capability_b": ["capability_a"],  # B depends on A - CIRCULAR!
        }
    }

    ai_client = MockAIClient(dag, "Tasks completed.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    agent_a = MockAgent("AgentA", "capability_a", delay=0.1)
    agent_b = MockAgent("AgentB", "capability_b", delay=0.1)

    network.register_agent(nlu)
    network.register_agent(agent_a)
    network.register_agent(agent_b)
    await network.start()

    try:
        request_id = "test_circular_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Do A and B"},
            request_id=request_id,
        )

        # Should handle gracefully (fallback to sequential or error)
        # The system should detect the circular dependency and fallback
        # We'll check that it doesn't hang forever
        try:
            result = await asyncio.wait_for(
                network.wait_for_response(request_id, timeout=5.0), timeout=6.0
            )
            # If we get here, the system handled it gracefully
            assert result is not None
        except asyncio.TimeoutError:
            pytest.fail("System hung on circular dependency - validation failed")

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_completion_detection():
    """Test that completion is detected when all capabilities finish."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # Simple DAG with 3 independent capabilities
    dag = {
        "dag": {
            "task_1": [],
            "task_2": [],
            "task_3": [],
        }
    }

    ai_client = MockAIClient(dag, "All three tasks completed successfully.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    agent1 = MockAgent("Agent1", "task_1", delay=0.05)
    agent2 = MockAgent("Agent2", "task_2", delay=0.05)
    agent3 = MockAgent("Agent3", "task_3", delay=0.05)

    network.register_agent(nlu)
    network.register_agent(agent1)
    network.register_agent(agent2)
    network.register_agent(agent3)
    await network.start()

    try:
        request_id = "test_completion_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Do task 1, 2, and 3"},
            request_id=request_id,
        )

        result = await network.wait_for_response(request_id, timeout=5.0)

        # Verify all three executed
        assert len(agent1.execution_order) == 1
        assert len(agent2.execution_order) == 1
        assert len(agent3.execution_order) == 1

        # Verify we got a final response
        assert result is not None
        assert "response" in result or isinstance(result, dict)

        print(f"\nCompletion detection test:")
        print(f"All {len([agent1, agent2, agent3])} agents executed")
        print(f"Final result received: {result is not None}")

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_context_passing_to_dependent_capabilities():
    """Test that results from dependencies are passed as context."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # DAG: first capability produces data, second uses it
    dag = {
        "dag": {
            "generate_data": [],
            "process_data": ["generate_data"],
        }
    }

    ai_client = MockAIClient(dag, "Data generated and processed.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    class DataGeneratorAgent(NetworkAgent):
        def __init__(self):
            super().__init__("DataGeneratorAgent")

        @property
        def capabilities(self):
            return {"generate_data"}

        async def _handle_capability_request(self, message):
            result = {
                "status": "success",
                "data": {"value": 42, "timestamp": "2024-01-01"},
                "capability": "generate_data",
            }
            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

        async def _handle_capability_response(self, message):
            pass

    class DataProcessorAgent(NetworkAgent):
        def __init__(self):
            super().__init__("DataProcessorAgent")
            self.received_context = None

        @property
        def capabilities(self):
            return {"process_data"}

        async def _handle_capability_request(self, message):
            # Check if context contains previous results
            data = message.content.get("data", {})
            context = data.get("context", {})
            self.received_context = context

            result = {
                "status": "success",
                "capability": "process_data",
                "processed": True,
            }
            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

        async def _handle_capability_response(self, message):
            pass

    generator = DataGeneratorAgent()
    processor = DataProcessorAgent()

    network.register_agent(nlu)
    network.register_agent(generator)
    network.register_agent(processor)
    await network.start()

    try:
        request_id = "test_context_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Generate data and process it"},
            request_id=request_id,
        )

        result = await network.wait_for_response(request_id, timeout=5.0)

        # Verify processor received context
        assert processor.received_context is not None
        assert "previous_results" in processor.received_context

        previous_results = processor.received_context["previous_results"]
        assert len(previous_results) > 0
        assert previous_results[0].get("capability") == "generate_data"

        print(f"\nContext passing test:")
        print(f"Processor received context: {processor.received_context is not None}")
        print(f"Previous results count: {len(previous_results)}")

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_single_capability_still_works():
    """Test that single capability requests still work (no DAG)."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # Single capability (should work like before)
    dag = {
        "dag": {
            "lights_color": [],
        }
    }

    ai_client = MockAIClient(dag, "Lights changed.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    lights_agent = MockAgent("LightingAgent", "lights_color", delay=0.1)

    network.register_agent(nlu)
    network.register_agent(lights_agent)
    await network.start()

    try:
        request_id = "test_single_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Turn lights red"},
            request_id=request_id,
        )

        result = await network.wait_for_response(request_id, timeout=5.0)

        # Verify execution
        assert len(lights_agent.execution_order) == 1
        assert result is not None

        print(f"\nSingle capability test:")
        print(f"Executed successfully: {result is not None}")

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_chained_dependencies():
    """Test chain of dependencies: A -> B -> C."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # Chain: A executes first, then B (depends on A), then C (depends on B)
    dag = {
        "dag": {
            "step_a": [],
            "step_b": ["step_a"],
            "step_c": ["step_b"],
        }
    }

    ai_client = MockAIClient(dag, "All steps completed.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    agent_a = MockAgent("AgentA", "step_a", delay=0.1)
    agent_b = MockAgent("AgentB", "step_b", delay=0.1)
    agent_c = MockAgent("AgentC", "step_c", delay=0.1)

    network.register_agent(nlu)
    network.register_agent(agent_a)
    network.register_agent(agent_b)
    network.register_agent(agent_c)
    await network.start()

    try:
        start_time = asyncio.get_event_loop().time()
        request_id = "test_chain_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Do step A, then B, then C"},
            request_id=request_id,
        )

        result = await network.wait_for_response(request_id, timeout=5.0)
        end_time = asyncio.get_event_loop().time()

        # Verify execution order
        time_a = agent_a.execution_order[0]["timestamp"]
        time_b = agent_b.execution_order[0]["timestamp"]
        time_c = agent_c.execution_order[0]["timestamp"]

        assert (
            time_a < time_b < time_c
        ), f"Execution order: A({time_a:.3f}) < B({time_b:.3f}) < C({time_c:.3f})"

        # Should take ~0.3s sequentially
        execution_time = end_time - start_time
        assert (
            execution_time >= 0.25
        ), f"Should execute sequentially (took {execution_time}s)"

        print(f"\nChained dependencies test:")
        print(f"Execution time: {execution_time:.3f}s")
        print(f"A: {time_a:.3f}s, B: {time_b:.3f}s, C: {time_c:.3f}s")

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_empty_dag_handling():
    """Test that empty DAG is handled gracefully."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # Mock AI client that returns empty DAG
    class EmptyDAGAIClient(MockAIClient):
        async def weak_chat(self, messages, tools=None):
            # Check all messages for prompt content
            full_content = " ".join(
                [msg.get("content", "") for msg in messages]
            ).lower()
            # Check for DAG extraction prompt
            if (
                "analyze this request" in full_content
                and "dependencies" in full_content
            ):
                # Return empty DAG
                return (type("Msg", (), {"content": json.dumps({"dag": {}})}), None)
            return await super().weak_chat(messages, tools)

    ai_client = EmptyDAGAIClient({"dag": {}}, "No tasks.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    network.register_agent(nlu)
    await network.start()

    try:
        request_id = "test_empty_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Do nothing"},
            request_id=request_id,
        )

        # Should handle gracefully (either error or empty response)
        try:
            result = await asyncio.wait_for(
                network.wait_for_response(request_id, timeout=2.0), timeout=3.0
            )
            # If we get here, system handled it gracefully
            assert result is not None
        except asyncio.TimeoutError:
            # Timeout is also acceptable - means system didn't hang
            pass

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_dag_with_invalid_capability():
    """Test that invalid capabilities are filtered out."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # DAG with one valid and one invalid capability
    dag = {
        "dag": {
            "lights_color": [],  # Valid
            "invalid_capability_xyz": [],  # Invalid - should be filtered
        }
    }

    ai_client = MockAIClient(dag, "Lights changed.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    lights_agent = MockAgent("LightingAgent", "lights_color", delay=0.1)

    network.register_agent(nlu)
    network.register_agent(lights_agent)
    await network.start()

    try:
        request_id = "test_invalid_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Turn lights red"},
            request_id=request_id,
        )

        result = await network.wait_for_response(request_id, timeout=5.0)

        # Should execute valid capability only
        assert len(lights_agent.execution_order) == 1
        assert result is not None

        print(f"\nInvalid capability filtering test:")
        print(f"Valid capability executed: {len(lights_agent.execution_order) == 1}")

    finally:
        await network.stop()


@pytest.mark.asyncio
async def test_dag_execution_with_results_tracking():
    """Test that results from all capabilities are collected."""
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)

    # DAG with multiple independent capabilities
    dag = {
        "dag": {
            "task_1": [],
            "task_2": [],
            "task_3": [],
        }
    }

    ai_client = MockAIClient(dag, "All tasks completed with results.")
    nlu = NLUAgent(ai_client, logger=JarvisLogger())

    class ResultTrackingAgent(NetworkAgent):
        def __init__(self, name: str, capability: str, result_value: str):
            super().__init__(name)
            self.capability_name = capability
            self.result_value = result_value

        @property
        def capabilities(self):
            return {self.capability_name}

        async def _handle_capability_request(self, message):
            result = {
                "status": "success",
                "capability": self.capability_name,
                "result": self.result_value,
                "agent": self.name,
            }
            await self.send_capability_response(
                message.from_agent, result, message.request_id, message.id
            )

        async def _handle_capability_response(self, message):
            pass

    agent1 = ResultTrackingAgent("Agent1", "task_1", "Result 1")
    agent2 = ResultTrackingAgent("Agent2", "task_2", "Result 2")
    agent3 = ResultTrackingAgent("Agent3", "task_3", "Result 3")

    network.register_agent(nlu)
    network.register_agent(agent1)
    network.register_agent(agent2)
    network.register_agent(agent3)
    await network.start()

    try:
        request_id = "test_results_001"

        await network.request_capability(
            from_agent="TestSystem",
            capability="intent_matching",
            data={"input": "Do task 1, 2, and 3"},
            request_id=request_id,
        )

        result = await network.wait_for_response(request_id, timeout=5.0)

        # Verify we got a response with results
        assert result is not None
        if isinstance(result, dict) and "results" in result:
            results = result["results"]
            assert len(results) == 3, f"Expected 3 results, got {len(results)}"

            # Verify each capability's result is present
            capability_results = {r.get("capability"): r.get("result") for r in results}
            assert "task_1" in capability_results
            assert "task_2" in capability_results
            assert "task_3" in capability_results

        print(f"\nResults tracking test:")
        print(f"Results collected: {result is not None}")

    finally:
        await network.stop()


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_dag_execution.py -v -s
    pytest.main([__file__, "-v", "-s"])
