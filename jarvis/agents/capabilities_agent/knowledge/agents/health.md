# HealthAgent

**Class**: `HealthAgent`
**Module**: `jarvis/agents/health_agent/__init__.py`
**Feature Flag**: `enable_health`

## Capabilities

### system_health_check
Full system health snapshot — agents, services, resources, incidents.
- "Is everything running?"
- "System health"
- "Any issues?"

### agent_health_status
Check responsiveness of registered agents.
- "Are all agents healthy?"
- "Is the calendar agent working?"

### service_health_status
Probe external service dependencies.
- "Is the calendar API up?"
- "Service status"

### system_resource_status
CPU, memory, disk, and event loop metrics.
- "How are system resources?"
- "CPU and memory usage?"

### health_report
Generate a detailed health report document.
- "Show health report"
- "Full health report"

### dependency_map
Visualize component dependency graph.
- "Show dependency map"
- "What depends on what?"

### incident_list
View active and recent incidents.
- "Any recent incidents?"
- "List active incidents"
- "What went wrong?"

## Background Monitoring
- Probes every 60 seconds (configurable: `health_probe_interval`)
- Reports every hour (configurable: `health_report_interval`)
- Reports saved to `~/.jarvis/health/`

## Incident System
1. **Detection**: Status transitions trigger incident creation
2. **Severity**: WARNING (degraded) or ERROR (unhealthy)
3. **Broadcast**: Health alerts sent to all agents on transitions
4. **Resolution**: Auto-resolves when component recovers
5. **Reports**: Incident reports written to disk

## What Gets Probed
- **Agents**: Registration and capability presence
- **Services**: Calendar API, SQLite, managed servers
- **Resources**: CPU, memory, disk usage, event loop lag
- **Network**: Message broker health, dropped messages, circuit breaker
