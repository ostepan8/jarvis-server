# System Skills

## Health Monitoring
**Agent**: HealthAgent
**Feature Flag**: `enable_health`

Continuous system health monitoring with probes, incident tracking, and reporting.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `system_health_check` | Full system health snapshot | "Is everything running?" |
| `agent_health_status` | Check agent responsiveness | "Are all agents healthy?" |
| `service_health_status` | Check external service health | "Is the calendar API up?" |
| `system_resource_status` | CPU, memory, disk, event loop | "How are system resources?" |
| `health_report` | Generate detailed health report | "Show health report" |
| `dependency_map` | Visualize component dependencies | "Show dependency map" |
| `incident_list` | View active/recent incidents | "Any recent incidents?" |

### Background Monitoring
- Probes run every 60 seconds (configurable)
- Monitors: agents, services (Calendar API, SQLite), resources (CPU, memory, disk, event loop)
- Automatic incident creation on status transitions
- Health alerts broadcast to all agents
- Reports written to `~/.jarvis/health/`

### Incident Lifecycle
1. Component transitions from healthy to degraded/unhealthy
2. Incident created automatically with severity and details
3. Alert broadcast to all agents
4. When component recovers, incident auto-resolves

---

## Server Management
**Agent**: ServerManagerAgent
**Feature Flag**: `enable_server_manager`

Manage external server processes (start, stop, restart, monitor).

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `register_server` | Register a new managed server | "Register the calendar server" |
| `start_server` | Start a managed server | "Start the calendar server" |
| `stop_server` | Stop a managed server | "Stop the calendar server" |
| `restart_server` | Restart a managed server | "Restart the calendar server" |
| `server_status` | Check server status | "Is the calendar server running?" |
| `list_servers` | List all managed servers | "What servers are registered?" |

### Features
- Server registry persisted to `~/.jarvis/servers.json`
- Health probes integrated with HealthAgent
- Monitor interval: 15 seconds (configurable)

---

## Night Mode
**Feature Flag**: `enable_night_mode`

Background agents that run during idle periods.

### Night Agents
| Agent | What It Does |
|-------|-------------|
| `NightModeControllerAgent` | Orchestrates night agent activation |
| `LogCleanupAgent` | Cleans old log files |
| `SelfImprovementAgent` | Analyzes codebase, creates improvement PRs |

### Self-Improvement
**Feature Flag**: `enable_self_improvement`
- Scans the codebase for improvement opportunities
- Can create tasks or pull requests
- Configurable: `self_improvement_use_prs` controls PR vs direct merge

---

## Capabilities Librarian
**Agent**: CapabilitiesAgent
**Feature Flag**: `enable_capabilities`

This agent. Maintains a living knowledge base of all Jarvis capabilities and answers questions about what the system can and cannot do.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `describe_capabilities` | Overview of all capabilities | "What can you do?" |
| `explain_capability` | Deep dive on a specific capability | "How does the calendar work?" |

### Progressive Disclosure
- Level 0: High-level domain summary (smart home, productivity, information, system)
- Level 1: Skill category breakdown with capability tables
- Level 2: Agent-specific details with examples and requirements

### Auto-Discovery
On startup, the agent introspects the agent network to identify which capabilities are actually live vs. documented but disabled. Responses reflect the current runtime state.
