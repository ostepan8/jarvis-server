# ProtocolAgent

**Class**: `ProtocolAgent`
**Module**: `jarvis/agents/protocol_agent/__init__.py`
**Always enabled**

## Capabilities

### execute_protocol
Run a saved multi-step workflow.
- "Run my morning routine"
- "Execute the deployment checklist"
- "Start the onboarding protocol"

### list_protocols
View available protocols.
- "What protocols do I have?"
- "List available workflows"
- "Show saved protocols"

## How Protocols Work

### Structure
Protocols are YAML-defined workflows with:
- **Steps**: Individual actions mapped to agent capabilities
- **Dependencies**: DAG structure defining execution order
- **Parameters**: Configurable inputs for each step

### Execution
1. Protocol YAML is parsed into a DAG
2. Steps with no dependencies execute in parallel
3. Dependent steps wait for their prerequisites
4. Results from earlier steps can feed into later ones
5. Final result aggregates all step outcomes

### Protocol Sources
- **Built-in**: `jarvis/protocols/defaults/` — system-provided workflows
- **Recorded**: `jarvis/protocols/recorded/` — user-created workflows

### Recording
Users can record new protocols by demonstrating a multi-step workflow. The system captures the sequence of capability invocations and saves them as a reusable protocol.
