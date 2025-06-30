"""Shared constants and enumerations for Jarvis."""

from enum import Enum

# Default network configuration
DEFAULT_PORT = 8000

# Default SQLite database for logs
LOG_DB_PATH = "jarvis_logs.db"

# Pre-defined protocol response phrases used when summarizing protocol results
# These names must match the protocol definitions exactly
PROTOCOL_RESPONSES = {
    "lights_on": [
        "All systems bright and ready, sir.",
        "Illuminating the manor, sir.",
        "Every light is now on, sir.",
    ],
    "lights_off": [
        "Lights out. Going dark, sir.",
        "Darkness engaged across the house, sir.",
        "Every light has been powered down, sir.",
    ],
    "Dim All Lights": [
        "Soft mood lighting in effect, sir.",
        "Light levels reduced for a calm ambience, sir.",
        "Dimming the house to a gentle glow, sir.",
    ],
    "Brighten All Lights": [
        "Maximizing illumination, sir.",
        "Lights set to full brilliance, sir.",
        "Raising brightness all the way, sir.",
    ],
    "Flash All Lights": [
        "Executing rapid flash sequence, sir.",
        "All lights flashing for attention, sir.",
        "Commencing strobe effect, sir.",
    ],
    "Light Color Control": [
        "Setting all lights to {color}, sir.",
        "The house now glows {color}, sir.",
        "Lights adjusted to a {color} hue, sir.",
    ],
    "Get Today's Events": [
        "Here's today's agenda, sir.",
        "Allow me to present your schedule for today, sir.",
        "These are your planned events for today, sir.",
    ],
}


class ExecutionResult(str, Enum):
    """Possible results of executing a protocol."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
