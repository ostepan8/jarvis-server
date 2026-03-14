# ChatAgent

**Class**: `ChatAgent`
**Module**: `jarvis/agents/chat_agent/agent.py`
**Always enabled**

## Capabilities

### chat
General-purpose conversation. The default fallback when no specific agent matches.
- "Hello"
- "Tell me a joke"
- "What do you think about AI?"
- "Let's talk about space"

### store_fact
Store a user preference or fact for future reference.
- "My favorite color is blue"
- "I prefer dark mode"
- "My dog's name is Max"

### get_facts
Retrieve stored user facts.
- "What do you know about me?"
- "What's my favorite color?"

### update_profile
Update the user's profile settings.
- "My timezone is EST"
- "I prefer metric units"

## Architecture
- Uses AI client for conversation generation
- Tool definitions in `tools/` for fact management
- Supports CollaborationMixin for multi-agent coordination
- Can act as lead agent in multi-step workflows
- Maintains conversation context via dialogue support

## Multi-Turn Dialogue
ChatAgent supports `dialogue_context` for agent-to-agent multi-turn conversations. When acting as lead agent, it can coordinate with specialists (e.g., ask SearchAgent for data, then discuss results with the user).

## Profile System
The AgentProfile tracks user preferences (timezone, units, communication style) and adapts responses accordingly.
