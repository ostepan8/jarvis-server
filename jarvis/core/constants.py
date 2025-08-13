"""Shared constants and enumerations for Jarvis."""

from enum import Enum

# Default network configuration
DEFAULT_PORT = 8000

# Default SQLite database for logs
LOG_DB_PATH = "jarvis_logs.db"



class ExecutionResult(str, Enum):
    """Possible results of executing a protocol."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"

