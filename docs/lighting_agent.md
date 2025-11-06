# Lighting Agent Documentation

The Lighting Agent provides a unified interface for controlling smart lights, regardless of whether you're using Phillips Hue, Yeelight, or other supported lighting systems. All operations work seamlessly across different hardware backends.

## Overview

The Lighting Agent allows you to control your smart lights through various commands:

- Turn lights on or off (individually or all at once)
- Adjust brightness levels
- Change colors by name
- Toggle lights on/off
- List and check the status of all lights

All operations run efficiently in parallel, meaning multiple lights respond simultaneously rather than sequentially.

## Available Methods

### Turning Lights On and Off

#### `turn_on_all_lights()`

Turns on every light connected to your system.

**What happens:** All lights that are reachable will turn on. If some lights fail to respond, you'll receive a message indicating how many succeeded and which ones failed.

**Example response:**

- Success: "Turned on all 9 lights"
- Partial success: "Turned on 8/9 lights (failed: 192.168.1.105)"

---

#### `turn_off_all_lights()`

Turns off every light connected to your system.

**What happens:** All lights will turn off. Similar to turning on, you'll be notified if any lights couldn't be controlled.

**Example response:**

- Success: "Turned off all 9 lights"
- Partial success: "Turned off 8/9 lights (failed: light_5)"

---

#### `turn_on_light(light_name)`

Turns on a specific light by its name or identifier.

**Parameters:**

- `light_name` (string): The name or IP address of the light you want to turn on

**What happens:** The specified light turns on. If the light name doesn't match any connected light, you'll receive an error message indicating the light wasn't found.

**Example responses:**

- Success: "Turned on 1 light(s)"
- Not found: "Light 'living room' not found"

---

#### `turn_off_light(light_name)`

Turns off a specific light by its name or identifier.

**Parameters:**

- `light_name` (string): The name or IP address of the light you want to turn off

**What happens:** The specified light turns off. Works similarly to `turn_on_light` but reverses the action.

---

#### `toggle_light(light_name)`

Switches a light's state—if it's on, it turns off; if it's off, it turns on.

**Parameters:**

- `light_name` (string): The name or IP address of the light to toggle

**What happens:** The system first checks the current state of the light, then reverses it. This is useful when you don't know or care what the current state is—you just want to flip it.

**Example response:** "Toggled 1 light(s)"

---

### Brightness Control

#### `set_all_brightness(brightness)`

Sets the brightness level for every light in your system.

**Parameters:**

- `brightness` (integer): A value between 0 and 254
  - `0` = Lights turn off completely
  - `1-253` = Various brightness levels (higher is brighter)
  - `254` = Maximum brightness

**What happens:** All lights adjust to the specified brightness level simultaneously. If you set brightness to 0, all lights will turn off. The system automatically converts brightness values to work correctly with your specific lighting hardware.

**Example responses:**

- Success: "Set brightness of all 9 lights to 128"
- Partial success: "Set brightness of 8/9 lights to 128 (failed: light_3)"

**Note:** The brightness scale (0-254) is universal and works the same way regardless of your lighting system. The agent handles any necessary conversions behind the scenes.

---

#### `set_brightness(light_name, brightness)`

Sets the brightness level for a specific light.

**Parameters:**

- `light_name` (string): The name or IP address of the light
- `brightness` (integer): A value between 0 and 254 (same scale as `set_all_brightness`)

**What happens:** Only the specified light adjusts its brightness. Setting brightness to 0 will turn that specific light off.

**Example response:** "Set brightness of 1 light(s) to 200"

---

### Color Control

#### `set_all_color(color_name)`

Changes all lights to the same color simultaneously.

**Parameters:**

- `color_name` (string): The name of the color. Supported colors include:
  - `red`
  - `orange`
  - `yellow`
  - `green`
  - `blue`
  - `purple`
  - `pink`
  - `white`

**What happens:** All lights change to the requested color at once. If you request an unsupported color, you'll receive an error message listing the available colors. The lights automatically turn on when changing colors (they can't display colors when off).

**Example responses:**

- Success: "Set all 9 lights to blue"
- Partial success: "Set 8/9 lights to blue (failed: light_2)"
- Invalid color: "Unknown color 'cyan'. Available colors: red, orange, yellow, green, blue, purple, pink, white"

---

#### `set_color_name(light_name, color_name)`

Changes a specific light to a named color.

**Parameters:**

- `light_name` (string): The name or IP address of the light
- `color_name` (string): One of the supported color names (same as `set_all_color`)

**What happens:** Only the specified light changes color. The light will automatically turn on if it was off.

**Example response:** "Set 1 light(s) to purple"

---

### Listing and Status

#### `list_lights()`

Returns information about all lights currently connected to your system.

**Returns:** A dictionary containing details about each light, including:

- Light identifier (ID or IP address)
- Light name (if available)
- Current state (on/off)
- Current brightness level (for some systems)
- Additional status information (like whether the light is reachable)

**What happens:** The system queries all connected lights and returns their current status. This is useful for discovering what lights are available and checking their current state.

**Example response structure:**

```json
{
  "192.168.1.100": {
    "id": "192.168.1.100",
    "name": "Living Room Light",
    "on": true,
    "brightness": 150
  },
  "192.168.1.101": {
    "id": "192.168.1.101",
    "name": "Kitchen Light",
    "on": false,
    "brightness": 0
  }
}
```

## How It Works

### Parallel Execution

When controlling multiple lights, all operations run simultaneously rather than one after another. This means:

- **Faster response times:** Controlling 9 lights takes roughly the same time as controlling 1 light
- **Better performance:** You'll notice operations complete much faster than before
- **Consistent experience:** The speed improvement works regardless of how many lights you have

### Error Handling

The system is designed to be resilient:

- **Partial success:** If some lights fail to respond, successful operations still complete
- **Detailed reporting:** You'll know exactly which lights succeeded and which failed
- **Error logging:** All failures are logged with specific details for troubleshooting

### Brightness Normalization

Different lighting systems use different brightness ranges:

- Some systems use 0-254
- Others use 1-100

The Lighting Agent automatically converts brightness values so you always use the same scale (0-254) regardless of your hardware. Setting brightness to 200 will give you the same relative brightness level whether you're using Hue or Yeelight bulbs.

### Color Mapping

Colors work the same way across all systems. When you request "blue," the system automatically converts it to the correct color format for your specific hardware. You don't need to worry about RGB values, hue numbers, or other technical details—just use color names.

## Usage Tips

1. **Use descriptive light names:** Give your lights meaningful names when setting them up. This makes it easier to control specific lights.

2. **Brightness values:**

   - For dim lighting: Use values around 50-100
   - For normal lighting: Use values around 128-180
   - For bright lighting: Use values above 200
   - To turn off: Use 0

3. **Checking before changes:** Use `list_lights()` to see all available lights and their current states before making changes.

4. **Partial failures:** Don't worry if some lights occasionally fail—this is normal with wireless devices. The system will report which lights didn't respond so you can troubleshoot.

## Backend Compatibility

All methods work identically regardless of which lighting backend you're using. The same commands work whether you have:

- Phillips Hue lights connected via bridge
- Yeelight bulbs connected directly
- Other supported lighting systems

The only difference is in initial configuration—once set up, all commands behave the same way.
