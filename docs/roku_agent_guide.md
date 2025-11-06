# Roku Agent Quick Start Guide

## What is the Roku Agent?

The Roku Agent is a new intelligent agent in the Jarvis system that allows you to control your Roku TV using natural language. It uses Roku's External Control Protocol (ECP) to send commands to your device over your local network.

## Quick Setup (3 steps)

### Step 1: Find Your Roku's IP Address

On your Roku device:

1. Press the Home button on your remote
2. Go to **Settings** → **Network** → **About**
3. Note the IP address (e.g., `192.168.1.150`)

### Step 2: Enable Network Access

On your Roku device:

1. Go to **Settings** → **System** → **Advanced system settings**
2. Select **Control by mobile apps** → **Network access**
3. Set it to **Default** or **Permissive**

### Step 3: Configure Your Environment

Add these lines to your `.env` file:

```bash
ROKU_IP_ADDRESS=192.168.1.150  # Use your actual Roku IP
ROKU_USERNAME=your-username    # Optional: for authenticated access
ROKU_PASSWORD=your-password    # Optional: for authenticated access
```

**Note:** Username and password are optional. The standard Roku ECP API doesn't require authentication, but they're available if you need them for development mode or special configurations.

That's it! The agent is now ready to use.

## Example Commands

Once configured, you can control your Roku using natural language:

### Launching Apps

```
"Open Netflix"
"Start YouTube"
"Launch Disney Plus"
"Go to Hulu"
```

### Playback Control

```
"Play"
"Pause"
"Fast forward"
"Rewind"
"Go back 10 seconds"
```

### Navigation

```
"Go home"
"Go back"
"Navigate down"
"Select"
"Move right 3 times"
```

### Volume Control

```
"Turn it up"
"Volume down"
"Mute"
"Increase volume 5 times"
```

### Power Control

```
"Turn on the TV"
"Turn off the TV"
"Power off"
```

### Input Switching

```
"Switch to HDMI 1"
"Change to HDMI 2"
```

### Information Queries

```
"What's playing?"
"List all apps"
"What apps are installed?"
"What's the device name?"
```

## How It Works

1. **You speak/type a command** - "Open Netflix"
2. **NLU Agent classifies** - Identifies this as a Roku command
3. **Roku Agent processes** - AI translates to function calls
4. **ECP API executes** - Sends HTTP request to Roku device
5. **You get a response** - "I've launched Netflix for you!"

## Testing Your Setup

Test your connection with:

```bash
curl http://YOUR_ROKU_IP:8060/query/device-info
```

If this returns XML with device information, you're all set!

## Troubleshooting

**Can't connect to Roku?**

- Verify IP address with `ping YOUR_ROKU_IP`
- Ensure both devices are on the same network
- Check that port 8060 is accessible
- Verify Network Access is not "Disabled"

**App not launching?**

- List all apps to see exact names
- Use the exact app name from the list
- Some apps may have special characters

**Commands not working?**

- Ensure Roku is powered on
- Try restarting the Roku device
- Check network connectivity

## Advanced Usage

### Programmatic Control

```python
from jarvis.agents.roku_agent import RokuAgent
from jarvis.ai_clients import OpenAIClient

ai_client = OpenAIClient(api_key="your-key")
roku = RokuAgent(ai_client=ai_client, device_ip="192.168.1.150")

# Natural language
result = await roku._process_roku_command("launch netflix")

# Direct service calls
await roku.roku_service.play()
await roku.roku_service.volume_up()

# Get information
apps = await roku.roku_service.list_apps()
device_info = await roku.roku_service.get_device_info()

await roku.close()
```

### Disable Roku Agent

If you don't want the Roku agent enabled:

```python
from jarvis.core.config import JarvisConfig, FeatureFlags

config = JarvisConfig(
    flags=FeatureFlags(enable_roku=False)
)
```

Or set in your environment:

```bash
# Not currently supported via env var, requires code change
```

## Available Capabilities

The Roku Agent provides these capabilities to the agent network:

- **Device Info**: Get model, version, network details
- **App Management**: List, search, launch apps
- **Playback**: Play, pause, rewind, fast forward
- **Navigation**: Directional controls, select, back, home
- **Volume**: Up, down, mute
- **Power**: On, off
- **Input**: Switch HDMI inputs
- **Search**: Search across channels
- **Player State**: Get current playback position and status

## Technical Details

- **Protocol**: Roku External Control Protocol (ECP)
- **Transport**: HTTP REST API on port 8060
- **Authentication**: None required (network-based security)
- **Dependencies**: httpx (already included)
- **Service**: `jarvis.services.roku_service.RokuService`
- **Agent**: `jarvis.agents.roku_agent.RokuAgent`

## Files Created

- `jarvis/services/roku_service.py` - ECP API client
- `jarvis/agents/roku_agent/agent.py` - Main agent
- `jarvis/agents/roku_agent/function_registry.py` - Capability mapping
- `jarvis/agents/roku_agent/command_processor.py` - AI command processing
- `jarvis/agents/roku_agent/tools/tools.py` - Tool definitions
- `jarvis/agents/roku_agent/README.md` - Detailed documentation
- `tests/test_roku_agent.py` - Test suite

## Learn More

- Full documentation: `jarvis/agents/roku_agent/README.md`
- Roku ECP Docs: https://developer.roku.com/docs/developer-program/debugging/external-control-api.md
- Run tests: `pytest tests/test_roku_agent.py -v`

## Support

If you encounter issues:

1. Check the troubleshooting section above
2. Verify your network configuration
3. Review the logs in `jarvis_logs.db`
4. Check the test suite passes: `pytest tests/test_roku_agent.py`

Enjoy controlling your Roku with natural language! 🎬📺
