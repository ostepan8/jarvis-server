# Lighting Agent

The lighting agent supports multiple lighting backends through a unified interface.

## Supported Backends

### Phillips Hue

- Configuration: Set `lighting_backend: "phillips_hue"` in config
- Requires: `hue_bridge_ip` (and optionally `hue_username`)
- Uses the `phue` library

### Yeelight

- Configuration: Set `lighting_backend: "yeelight"` in config
- Optional: `yeelight_bulb_ips` (list of IPs) - if not provided, auto-discovers bulbs
- Uses the `yeelight` library

## Usage

The agent is automatically created by the factory based on configuration:

```python
config = JarvisConfig(
    lighting_backend="yeelight",  # or "phillips_hue"
    yeelight_bulb_ips=["192.168.1.100", "192.168.1.101"],  # Optional for Yeelight
    # OR for Hue:
    # hue_bridge_ip="192.168.1.50",
    # hue_username="your-username",
)
```

## Protocol Compatibility

Protocols reference the agent as `"PhillipsHueAgent"` for backward compatibility.
The unified `LightingAgent` is registered with this alias when using Phillips Hue backend,
and can be used with Yeelight as well.

All protocol functions work the same way:

- `turn_on_all_lights()`
- `turn_off_all_lights()`
- `set_all_color(color_name)`
- `set_all_brightness(brightness)`

## Architecture

- `BaseLightingBackend`: Abstract interface defining lighting operations
- `PhillipsHueBackend`: Hue-specific implementation
- `YeelightBackend`: Yeelight-specific implementation
- `LightingAgent`: Unified agent that wraps a backend
- `create_lighting_agent()`: Factory function to create agents

## Adding New Backends

To add a new backend:

1. Inherit from `BaseLightingBackend`
2. Implement all abstract methods
3. Update `create_lighting_agent()` to support the new backend type
4. Add configuration options to `JarvisConfig`
