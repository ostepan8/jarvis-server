# Jarvis Capabilities Index

Jarvis is a multi-agent AI assistant that orchestrates specialized agents to handle a wide range of tasks. Capabilities are organized into four domains.

## Skill Domains

### Smart Home
Control lighting, television, and monitor device health across your connected home.
- **Lighting**: Color, brightness, toggle, status (Phillips Hue, Yeelight)
- **Television**: Roku navigation, playback, volume, app launching, multi-device
- **Device Monitoring**: CPU, memory, disk, thermals, diagnostics, cleanup, trends

### Productivity
Manage your calendar, tasks, schedules, and workflows.
- **Calendar**: Create, list, modify, delete events
- **Tasks**: Create, list, update, complete, delete tasks (kanban-style board)
- **Scheduling**: Reminders, recurring schedules, cron-like automation
- **Protocols**: Execute recorded multi-step workflows (DAG-based)

### Information
Search the web, store and retrieve memories, and have conversations.
- **Search**: Web search, news search, fact lookup
- **Memory**: Store facts, recall information, vector search, markdown vault
- **Chat**: General conversation, fact storage, profile management
- **Canvas**: Course listings, homework and assignment tracking

### System
Monitor and manage the Jarvis system itself.
- **Health**: System health checks, health reports, incident tracking, dependency maps
- **Device Monitor**: Host hardware watchdog with background monitoring and alerts
- **Server Manager**: Register, start, stop, restart managed server processes
- **Night Mode**: Background agents for log cleanup and self-improvement

## How Routing Works

1. User input arrives at the NLU (Natural Language Understanding) agent
2. Fast-path classifier attempts embedding-based matching (sub-millisecond)
3. If confidence is low, LLM classification builds a capability DAG
4. Capabilities execute in parallel where dependencies allow
5. Results aggregate into a single response

## Active Capabilities

The system discovers capabilities dynamically at startup. Each agent registers its capabilities with the agent network, and the NLU routes to them automatically. Ask about a specific domain or agent for details.
