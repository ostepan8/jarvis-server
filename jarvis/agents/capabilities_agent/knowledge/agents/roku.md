# RokuAgent

**Class**: `RokuAgent`
**Module**: `jarvis/agents/roku_agent/agent.py`
**Feature Flag**: `enable_roku`

## Capabilities

### play_app
Launch a streaming app on Roku.
- "Open Netflix"
- "Launch YouTube"
- "Start Disney+"

### navigate
Navigate Roku menus and UI.
- "Go to home on the TV"
- "Go back"
- "Press home on Roku"

### type
Type text into search fields or text inputs.
- "Type 'Breaking Bad' on the TV"
- "Search for 'comedy movies'"

### press_button
Simulate remote button presses.
- "Press play"
- "Press pause"
- "Hit the back button"
- Volume up/down, mute

### get_status
Check what's currently playing or device state.
- "What's playing on the TV?"
- "Is the TV on?"
- "What app is open?"

## Multi-Device Support
- Register multiple devices via `ROKU_IP_ADDRESSES` (comma-separated)
- Single device via `ROKU_IP_ADDRESS`
- Devices auto-probed for serial, model, and name at startup
- Target specific devices by name: "Pause the bedroom TV"
- Default device used when no target specified
- Device registry persisted to disk

## Architecture
- `RokuDeviceRegistry` manages device discovery and persistence
- `RokuService` handles ECP (External Control Protocol) HTTP calls
- `command_processor.py` parses natural language into Roku commands
- `function_registry.py` maps capabilities to handler functions
- SSH trigger support for remote control scenarios

## Environment Variables
- `ROKU_IP_ADDRESS`: Single Roku device IP
- `ROKU_IP_ADDRESSES`: Comma-separated list for multi-device
- `ROKU_USERNAME`: Optional authentication
- `ROKU_PASSWORD`: Optional authentication
