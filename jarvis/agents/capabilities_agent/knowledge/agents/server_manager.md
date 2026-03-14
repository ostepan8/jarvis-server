# ServerManagerAgent

**Class**: `ServerManagerAgent`
**Module**: `jarvis/agents/server_manager_agent/__init__.py`
**Feature Flag**: `enable_server_manager`

## Capabilities

### register_server
Register a new server process for management.
- "Register the calendar server at localhost:8080"
- "Add a new managed server"

### start_server
Start a registered server process.
- "Start the calendar server"
- "Boot up the API server"

### stop_server
Stop a running managed server.
- "Stop the calendar server"
- "Shut down the API server"

### restart_server
Restart a managed server (stop + start).
- "Restart the calendar server"
- "Reboot the API"

### server_status
Check if a managed server is running.
- "Is the calendar server running?"
- "Check server status"

### list_servers
List all registered managed servers.
- "What servers are registered?"
- "Show managed servers"

## Architecture
- `ServerManagerService` manages process lifecycle
- Server registry persisted to `~/.jarvis/servers.json` (configurable: `server_registry_path`)
- Background monitor checks server health every 15 seconds (configurable: `server_monitor_interval`)
- Health probes integrate with HealthAgent for system-wide monitoring
- `models.py` defines server data structures
