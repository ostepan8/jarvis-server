"""Shared constants and enumerations for Jarvis."""

from enum import Enum

# Default network configuration
DEFAULT_PORT = 8000

# Default SQLite database for logs
LOG_DB_PATH = "jarvis_logs.db"

# Pre-defined protocol response phrases used when summarizing protocol results
PROTOCOL_RESPONSES = {
    "lights_on": [
        "All lights have been successfully activated, sir.",
        "The entire residence is now fully illuminated, sir.",
        "Lighting systems are online, as requested, sir.",
        "I've restored full illumination to the manor, sir.",
        "Every light in the building has been switched on, sir.",
        "The manor's lighting grid is fully operational, sir.",
        "All ambient lights are active now, sir.",
        "Lights powered up and ready for your convenience, sir.",
        "Full lighting mode engaged throughout the premises, sir.",
        "The lighting systems are functioning at full capacity, sir.",
    ],
    "lights_off": [
        "All lighting systems have been disengaged, sir.",
        "The manor is now darkened, sir.",
        "Lighting has been powered down completely, sir.",
        "Dark mode successfully initiated across the residence, sir.",
        "I've disabled all illumination, sir.",
        "The residence is in blackout mode, sir.",
        "All lights have been extinguished, sir.",
        "Illumination protocols have been terminated, sir.",
        "I've placed the house into low-power darkness mode, sir.",
        "Lights are offline as requested, sir.",
    ],
    "Dim All Lights": [
        "Lighting dimmed precisely to your specifications, sir.",
        "I've adjusted the lights for a subtle ambiance, sir.",
        "Mood lighting protocol successfully engaged, sir.",
        "I've set all lighting to a comfortable level, sir.",
        "The illumination has been reduced to optimal comfort, sir.",
        "Ambient lighting now in effect, sir.",
        "Lights dimmed to create the desired atmosphere, sir.",
        "Soft lighting activated throughout the manor, sir.",
        "Lighting intensity reduced for relaxation, sir.",
        "Dimmed lighting mode is now active, sir.",
    ],
    "Brighten All Lights": [
        "Illumination levels maximized throughout the manor, sir.",
        "All lights brightened to their fullest intensity, sir.",
        "Lighting raised to maximum brightness, sir.",
        "I've restored lights to full luminosity, sir.",
        "Bright lighting protocol completed successfully, sir.",
        "The house is now exceptionally well-lit, sir.",
        "Full brightness achieved across all rooms, sir.",
        "Illumination adjusted to maximum clarity, sir.",
        "Lighting intensity set to highest available levels, sir.",
        "I've engaged maximum illumination mode, sir.",
    ],
    "Flash All Lights": [
        "Flash sequence completed successfully, sir.",
        "Lights have flashed precisely as you requested, sir.",
        "Strobe lighting effect executed successfully, sir.",
        "Rapid flash protocol concluded, sir.",
        "All lighting briefly set to flash mode, sir.",
        "Attention-grabbing flash sequence now complete, sir.",
        "The lights have executed the flash routine, sir.",
        "Lighting has briefly cycled through strobe mode, sir.",
        "Flash operation has been performed without issue, sir.",
        "Rapid illumination pulses have concluded, sir.",
    ],
    "Light Color Control": [
        "All lights have been set to {color}, sir.",
        "Lighting adjusted precisely to a {color} hue, sir.",
        "The manor now features {color} illumination, sir.",
        "I've completed your requested color adjustment to {color}, sir.",
        "All ambient lights display {color}, as desired, sir.",
        "Lighting systems are now emitting a {color} glow, sir.",
        "The color of illumination has been changed to {color}, sir.",
        "Lights throughout the residence are now {color}, sir.",
        "Lighting color protocol successfully activated: {color}, sir.",
        "I've switched lighting color to your requested {color}, sir.",
    ],
    "Get Today's Events": [
        "I've assembled today's schedule for your review, sir.",
        "Your daily agenda has been successfully retrieved, sir.",
        "Today's appointments and events are ready, sir.",
        "I've compiled the day's planned activities, sir.",
        "Here's today's itinerary, fully updated, sir.",
        "Schedule for today has been organized as requested, sir.",
        "I've prepared today's event summary, sir.",
        "Your calendar events for the day have been accessed, sir.",
        "Today's engagements have been arranged and ready, sir.",
        "All events and meetings for today are now available, sir.",
    ],
}


class ExecutionResult(str, Enum):
    """Possible results of executing a protocol."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
