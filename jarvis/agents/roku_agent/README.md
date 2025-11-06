# Roku Agent

The Roku Agent enables natural language control of Roku TV devices through the External Control Protocol (ECP). This agent allows you to control your Roku device using conversational commands.

## Features

### Device Information

- Get device details (model, software version, network info)
- Query currently active app/channel
- List all installed apps
- Check media player state and playback position

### App/Channel Control

- Launch apps by name (e.g., "open Netflix", "start YouTube")
- Search for and discover installed apps
- Switch between channels seamlessly

### Playback Control

- Play/pause media
- Fast forward and rewind
- Instant replay (jump back a few seconds)
- Full media player control

### Navigation

- Navigate menus using directional controls (up, down, left, right)
- Select items
- Go back to previous screens
- Return to home screen
- Multi-step navigation support

### Volume and Power

- Adjust volume up/down with count support
- Mute/unmute audio
- Power on/off the device

### Input Switching

- Switch between HDMI inputs (HDMI1-4)
- Access tuner input
- Control TV inputs for Roku TVs

### Search

- Search for content across all channels
- Type queries automatically

## Setup

### 1. Find Your Roku Device IP Address

You can find your Roku device's IP address by:

- Going to Settings → Network → About on your Roku device
- Using your router's admin panel to see connected devices
- Using network scanning tools like `nmap` or `arp -a`

### 2. Enable Network Access

On your Roku device:

1. Go to Settings → System → Advanced system settings
2. Select "Control by mobile apps"
3. Choose "Network access"
4. Set it to "Default" or "Permissive" to allow external control

### 3. Configure Environment Variables

Add your Roku device settings to your `.env` file:

```bash
ROKU_IP_ADDRESS=192.168.1.150  # Replace with your Roku's IP address
ROKU_USERNAME=your-username    # Optional: for authenticated access
ROKU_PASSWORD=your-password    # Optional: for authenticated access
```

**Note:** Username and password are optional and typically not required for standard Roku ECP control. They're provided for special configurations like developer mode access.

### 4. Enable the Roku Agent

The agent is enabled by default. To disable it, modify your config:

```python
from jarvis.core.config import JarvisConfig, FeatureFlags

config = JarvisConfig(
    flags=FeatureFlags(enable_roku=False)  # Disable Roku agent
)
```

## Usage Examples

### Natural Language Commands

The Roku agent understands natural language commands:

```python
# Launch apps
"Open Netflix"
"Start YouTube"
"Launch Disney Plus"

# Playback control
"Play"
"Pause"
"Fast forward"
"Rewind 10 seconds"

# Navigation
"Go home"
"Go back"
"Navigate down 3 times"
"Select"

# Volume control
"Turn it up"
"Volume down"
"Mute"
"Increase volume 5 times"

# Power control
"Turn on the TV"
"Turn off"

# Input switching
"Switch to HDMI 1"
"Change to HDMI 2"

# Information queries
"What's playing?"
"List all apps"
"What apps are installed?"
```

### Programmatic Usage

```python
from jarvis.agents.roku_agent import RokuAgent
from jarvis.ai_clients import OpenAIClient

# Initialize the agent
ai_client = OpenAIClient(api_key="your-openai-key")
roku_agent = RokuAgent(
    ai_client=ai_client,
    device_ip="192.168.1.150"
)

# Process natural language commands
result = await roku_agent._process_roku_command("launch netflix")
print(result["response"])  # "I've launched Netflix for you!"

# Direct service calls
await roku_agent.roku_service.play()
await roku_agent.roku_service.volume_up()
await roku_agent.roku_service.home()

# Get device information
device_info = await roku_agent.roku_service.get_device_info()
print(device_info["device_name"])
print(device_info["model"])

# List installed apps
apps = await roku_agent.roku_service.list_apps()
for app in apps["apps"]:
    print(f"{app['name']} (ID: {app['id']})")

# Clean up
await roku_agent.close()
```

## Architecture

The Roku Agent follows the standard agent pattern in the Jarvis system:

### Components

1. **RokuService** (`jarvis/services/roku_service.py`)

   - Handles HTTP communication with the Roku device
   - Implements the External Control Protocol (ECP)
   - Provides async methods for all Roku operations

2. **RokuAgent** (`jarvis/agents/roku_agent/agent.py`)

   - Main agent class that inherits from `NetworkAgent`
   - Handles capability requests from the agent network
   - Manages lifecycle and resource cleanup

3. **RokuFunctionRegistry** (`jarvis/agents/roku_agent/function_registry.py`)

   - Maps capability names to service methods
   - Handles parameter transformation and validation
   - Provides count-based operations (e.g., volume_up multiple times)

4. **RokuCommandProcessor** (`jarvis/agents/roku_agent/command_processor.py`)

   - Processes natural language commands using AI
   - Orchestrates tool calls and function execution
   - Generates conversational responses

5. **Tools** (`jarvis/agents/roku_agent/tools/tools.py`)
   - Defines tool schemas for the AI
   - Specifies available functions and their parameters

## Capabilities

The agent exposes the following capabilities to the agent network:

- `roku_command` - Main entry point for natural language commands
- `roku_device_info` - Get device information
- `roku_active_app` - Query active app/channel
- `roku_list_apps` - List all installed apps
- `roku_player_info` - Get media player state
- `roku_launch_app` - Launch an app/channel
- `roku_play` - Resume playback
- `roku_pause` - Pause playback
- `roku_rewind` - Rewind media
- `roku_fast_forward` - Fast forward media
- `roku_instant_replay` - Jump back a few seconds
- `roku_home` - Go to home screen
- `roku_back` - Go back
- `roku_select` - Select/OK button
- `roku_navigate` - Directional navigation
- `roku_volume_up` - Increase volume
- `roku_volume_down` - Decrease volume
- `roku_volume_mute` - Mute/unmute
- `roku_power_off` - Turn off device
- `roku_power_on` - Turn on device
- `roku_switch_input` - Switch HDMI input
- `roku_search` - Search for content

## Roku External Control Protocol (ECP)

The agent uses Roku's REST API for device control. Key endpoints:

- `http://<device-ip>:8060/query/device-info` - Device information
- `http://<device-ip>:8060/query/apps` - List apps
- `http://<device-ip>:8060/query/active-app` - Active app
- `http://<device-ip>:8060/launch/<app-id>` - Launch app
- `http://<device-ip>:8060/keypress/<key>` - Send key press

All API calls are made over HTTP on port 8060. No authentication is required, but network access must be enabled on the device.

## Troubleshooting

### Connection Issues

If you can't connect to your Roku device:

1. **Verify IP Address**: Make sure the IP address is correct

   ```bash
   ping 192.168.1.150  # Replace with your Roku's IP
   ```

2. **Check Network Access Settings**: Ensure "Network access" is not set to "Disabled"

3. **Verify Port Access**: Test that port 8060 is accessible

   ```bash
   curl http://192.168.1.150:8060/query/device-info
   ```

4. **Same Network**: Ensure your computer and Roku are on the same network

### App Not Found

If launching apps fails:

1. List all apps to verify the correct name:

   ```python
   apps = await roku_agent.roku_service.list_apps()
   ```

2. Use the exact app name as shown in the list

3. Some apps may have special characters or unexpected naming

### Device Not Responding

If commands aren't working:

1. Check if the device is powered on
2. Try restarting your Roku device
3. Verify the device firmware is up to date
4. Check for network connectivity issues

## Testing

Run the test suite:

```bash
pytest tests/test_roku_agent.py -v
```

The tests cover:

- Agent initialization
- Service method availability
- Capability exposure
- Request handling
- Function registry mapping
- Power operations

## References

- [Roku External Control Protocol Documentation](https://developer.roku.com/docs/developer-program/debugging/external-control-api.md)
- [Roku Developer Setup Guide](https://developer.roku.com/docs/developer-program/getting-started/roku-dev-prog.md)

## Contributing

When adding new features:

1. Add methods to `RokuService` for new ECP endpoints
2. Update the function registry with capability mappings
3. Add tool definitions in `tools/tools.py`
4. Update system prompts in `command_processor.py` if needed
5. Add tests to `tests/test_roku_agent.py`
6. Update this README with new capabilities
