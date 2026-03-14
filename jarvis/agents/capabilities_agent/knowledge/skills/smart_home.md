# Smart Home Skills

## Lighting Control
**Agent**: LightingAgent
**Backends**: Phillips Hue, Yeelight
**Feature Flag**: `enable_lights`

Control smart lights throughout your home. Supports multiple lighting backends with a unified interface.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `lights_on` | Turn lights on | "Turn on the lights" |
| `lights_off` | Turn lights off | "Kill the lights" |
| `lights_color` | Set light color | "Make the lights blue" |
| `lights_brightness` | Adjust brightness | "Dim the lights to 30%" |
| `lights_toggle` | Toggle on/off state | "Toggle the lights" |
| `lights_list` | List connected lights | "What lights do I have?" |
| `lights_status` | Check current state | "Are the lights on?" |

### Requirements
- Phillips Hue: Bridge IP and username configured
- Yeelight: Bulb IPs configured
- Set `LIGHTING_BACKEND` to `phillips_hue` or `yeelight`

---

## Television Control
**Agent**: RokuAgent
**Feature Flag**: `enable_roku`

Control Roku-powered TVs with voice commands. Supports multi-device setups with device targeting.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `play_app` | Launch an app | "Open Netflix" |
| `navigate` | Navigate menus | "Go to home on the TV" |
| `type` | Type text on screen | "Type 'movie title' on Roku" |
| `press_button` | Press a remote button | "Press play on the TV" |
| `get_status` | Check device status | "What's playing on the TV?" |
| Volume control | Adjust volume | "Turn up the volume" |

### Multi-Device Support
- Multiple Roku devices can be registered via `ROKU_IP_ADDRESSES`
- Target specific devices: "Pause the bedroom TV"
- Default device used when no target specified
- SSH-triggered commands for remote control scenarios

### Requirements
- At least one Roku device IP configured
- Optional: Username/password for restricted features

---

## Device Monitoring
**Agent**: DeviceMonitorAgent
**Feature Flag**: `enable_device_monitor`

Monitors host hardware metrics with background probing, alerts, and trend analysis.

### What You Can Do
| Capability | Description | Example |
|-----------|-------------|---------|
| `device_status` | Current CPU, memory, disk, thermals | "How's my computer doing?" |
| `device_diagnostics` | Top processes, resource hogs | "What's eating all my RAM?" |
| `device_cleanup` | Clean temp files, free disk space | "Clean up temp files" |
| `device_history` | Metric trends over time | "Has CPU been high all day?" |

### Background Monitoring
- Probes run every 30 seconds (configurable via `device_monitor_probe_interval`)
- Metrics stored in time-series format for trend analysis
- Alerts broadcast to all agents when thresholds exceeded
