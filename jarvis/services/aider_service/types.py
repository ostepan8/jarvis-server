"""
Core types and data structures for the Aider CLI Service.

This module defines the base types, enums, and result structures
used throughout the Aider CLI service architecture.
"""

import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class AiderMode(Enum):
    """Aider interaction modes"""

    MESSAGE = "message"
    YES = "yes"
    COMMIT = "commit"
    TEST = "test"
    LINT = "lint"


@dataclass
class AiderResult:
    """Structured result from any CLI operation"""

    success: bool
    stdout: str
    stderr: str
    exit_code: int
    command: str
    duration: float
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary"""
        return {
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "command": self.command,
            "duration": self.duration,
            "error_message": self.error_message,
        }

    @classmethod
    def success_result(
        cls, stdout: str = "", command: str = "", duration: float = 0.0
    ) -> "AiderResult":
        """Create a successful result"""
        return cls(
            success=True,
            stdout=stdout,
            stderr="",
            exit_code=0,
            command=command,
            duration=duration,
        )

    @classmethod
    def error_result(
        cls,
        error_message: str,
        command: str = "",
        stderr: str = "",
        exit_code: int = 1,
        duration: float = 0.0,
    ) -> "AiderResult":
        """Create an error result"""
        return cls(
            success=False,
            stdout="",
            stderr=stderr or error_message,
            exit_code=exit_code,
            command=command,
            duration=duration,
            error_message=error_message,
        )


class ServiceError(Exception):
    """Base exception for service errors"""

    pass


class AiderNotFoundError(ServiceError):
    """Raised when aider executable is not found"""

    pass


class GitOperationError(ServiceError):
    """Raised when git operations fail"""

    pass


class FileOperationError(ServiceError):
    """Raised when file operations fail"""

    pass


class GitHubOperationError(ServiceError):
    """Raised when GitHub operations fail"""

    pass
