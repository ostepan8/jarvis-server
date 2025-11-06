# Routing Flow Tests

This directory contains tests for verifying the decentralized agent routing network.

## Quick Start

### Run Mock Tests (No API keys needed)

```bash
# Run all routing tests
pytest tests/test_nlu_routing.py -v -s

# Run specific test
pytest tests/test_nlu_routing.py::test_simple_nlu_to_agent_routing -v -s
```

### Run with Real LLM (Requires OPENAI_API_KEY)

```bash
# Set environment variable
export USE_REAL_LLM=1
export OPENAI_API_KEY=your_key_here

# Run real LLM test
pytest tests/test_nlu_routing.py::test_real_llm_routing -v -s
```

### Interactive Testing

```bash
# Interactive mode (uses mocks by default)
python tests/test_routing_interactive.py --interactive

# With real LLM
python tests/test_routing_interactive.py --interactive --real-llm

# Single test
python tests/test_routing_interactive.py --input "Turn on the lights"
```

## Test Output

Tests will show:

1. **Routing Flow**: Step-by-step agent communication path

   ```
   Flow for request_id: test_001
   ============================================================
   1. NLUAgent → ALL
      Capability: control_lights
   2. LightingAgent → NLUAgent
      Type: response
   ============================================================
   ```

2. **Agent Participants**: Which agents were involved

   ```
   Agents involved: NLUAgent, LightingAgent
   ```

3. **Capability Usage**: Which capabilities were requested
   ```
   CAPABILITY USAGE:
   control_lights: 1 request(s)
     - NLUAgent → ALL
   ```

## Writing New Tests

```python
import pytest
from tests.tools.routing_tracker import RoutingTracker, wrap_network_with_tracker

@pytest.mark.asyncio
async def test_my_flow():
    tracker = RoutingTracker()
    network = AgentNetwork()
    wrap_network_with_tracker(network, tracker)  # Enable tracking

    # ... setup agents ...

    # Make request
    request_id = "test_001"
    await network.request_capability(...)

    # Verify flow
    flow = tracker.get_flow(request_id)
    print(tracker.format_flow_diagram(request_id))

    # Assertions
    assert "NLUAgent" in flow[0]
    assert "expected_agent → response" in flow[-1]
```

## Test Examples

### Simple Routing

```python
await test_routing_flow("Turn on the lights")
# Expected: NLU → Lights → NLU → System
```

### Multi-Step

```python
await test_routing_flow("Turn on lights and check my calendar")
# Expected: NLU → Lights → NLU → Calendar → NLU → System
```

### Agent-Initiated Follow-up

```python
await test_routing_flow("Turn on lights")
# If agent detects need: Lights → NLU → Calendar → NLU → System
```

## Routing Tracker API

The `RoutingTracker` provides:

- `get_flow(request_id)` - Get flow as list of strings
- `get_flow_verbose(request_id)` - Get flow as event objects
- `get_agent_participants(request_id)` - Get list of agents involved
- `get_capability_usage(capability)` - Get all events for a capability
- `assert_path(request_id, expected_path)` - Assert flow matches expected
- `format_flow_diagram(request_id)` - Pretty-print flow

## Assertions

```python
# Assert specific path
assert tracker.assert_path(
    request_id,
    [
        "NLUAgent → ALL [control_lights]",
        "LightingAgent → NLUAgent [response]"
    ]
)

# Assert agents participated
participants = tracker.get_agent_participants(request_id)
assert "NLUAgent" in participants
assert "LightingAgent" in participants

# Assert capability was used
events = tracker.get_capability_usage("control_lights")
assert len(events) > 0
```
