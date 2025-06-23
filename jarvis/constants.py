"""Shared constants and enumerations for Jarvis."""

from enum import Enum

# Default network configuration
DEFAULT_PORT = 8000

# Default SQLite database for logs
LOG_DB_PATH = "jarvis_logs.db"

# Pre-defined protocol response phrases used when summarizing protocol results
PROTOCOL_RESPONSES = {
    "blue_lights_on": "Blue lights activated, sir.",
    "blue_lights_off": "Blue lights deactivated, sir.",
    "red_alert": "Red alert mode engaged. All systems on high alert, sir.",
    "all_lights_off": "All lights have been turned off, sir.",
    "dim_lights": "Lights dimmed to comfortable levels, sir.",
    "bright_lights": "Lights set to maximum brightness, sir.",
    "morning_routine": "Good morning, sir. Your morning routine has been initiated.",
    "goodnight": "Goodnight, sir. Sleep mode activated.",
}


class ExecutionResult(str, Enum):
    """Possible results of executing a protocol."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
