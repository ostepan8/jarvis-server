# LightingAgent

**Class**: `LightingAgent`
**Module**: `jarvis/agents/lights_agent/lighting_agent.py`
**Feature Flag**: `enable_lights`
**Backends**: Phillips Hue (`phillips_hue_backend.py`), Yeelight (`yeelight_backend.py`)

## Capabilities

### lights_on
Turn lights on. Accepts optional room/group targeting.
- "Turn on the lights"
- "Turn on the bedroom lights"
- "Light up the living room"

### lights_off
Turn lights off.
- "Turn off the lights"
- "Kill the lights"
- "Lights off in the kitchen"

### lights_color
Set light color by name or hex value.
- "Make the lights red"
- "Change lights to blue"
- "Set the lights to warm white"
- Supported colors depend on backend capabilities

### lights_brightness
Adjust brightness (0-100 scale).
- "Dim the lights to 30%"
- "Set brightness to max"
- "Make it brighter"
- "Turn down the lights"

### lights_toggle
Toggle current on/off state.
- "Toggle the lights"
- "Flip the lights"

### lights_list
List all connected/discovered lights.
- "What lights do I have?"
- "Show me the lights"
- "How many lights are connected?"

### lights_status
Query current state of lights (on/off, color, brightness).
- "Are the lights on?"
- "What color are the lights?"
- "Light status"

## Architecture
- Uses a backend abstraction layer (`backend.py`)
- Backend selected via `LIGHTING_BACKEND` environment variable
- AI client used for natural language command parsing
- Tool definitions in `tools.py`

## Environment Variables
- `LIGHTING_BACKEND`: `phillips_hue` or `yeelight`
- `PHILLIPS_HUE_BRIDGE_IP`: Hue bridge IP address
- `PHILLIPS_HUE_USERNAME`: Hue API username
- `YEELIGHT_BULB_IPS`: Comma-separated bulb IPs
