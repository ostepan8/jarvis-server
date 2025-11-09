"""Standardized error handling for Jarvis agents and services.

This module provides a consistent error hierarchy and response format
for all agents and services in the Jarvis system.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


class AgentError(Exception):
    """Base exception for all agent-related errors.
    
    All custom agent exceptions should inherit from this class
    to enable consistent error handling across the system.
    """
    
    def __init__(
        self,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        retry_after: Optional[int] = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.retry_after = retry_after
    
    @property
    def error_type(self) -> str:
        """Return the error type name."""
        return self.__class__.__name__
    
    def to_response(self) -> "ErrorResponse":
        """Convert exception to standardized ErrorResponse."""
        return ErrorResponse(
            error_type=self.error_type,
            message=self.message,
            details=self.details,
            retry_after=self.retry_after,
        )


class ServiceUnavailableError(AgentError):
    """Raised when an external service is unavailable or unreachable.
    
    This error is typically used for network failures, service timeouts,
    or when a required external service is down.
    """
    pass


class InvalidParameterError(AgentError):
    """Raised when invalid parameters are provided to an agent or service.
    
    This includes missing required parameters, parameters with invalid types,
    or parameter values that are out of acceptable ranges.
    """
    pass


class AuthenticationError(AgentError):
    """Raised when authentication or authorization fails.
    
    This includes invalid API keys, expired tokens, or insufficient
    permissions to perform the requested operation.
    """
    pass


class TimeoutError(AgentError):
    """Raised when an operation exceeds its time limit.
    
    This can occur during agent communication, external API calls,
    or long-running operations.
    """
    pass


class ProtocolExecutionError(AgentError):
    """Raised when protocol execution fails.
    
    This includes errors during protocol step execution, validation
    failures, or when a protocol cannot be completed.
    """
    pass


class CapabilityNotFoundError(AgentError):
    """Raised when a requested capability is not available.
    
    This occurs when an agent is asked to perform a capability
    it doesn't support, or when no agent provides the requested capability.
    """
    pass


class ConfigurationError(AgentError):
    """Raised when configuration is missing or invalid.
    
    This includes missing environment variables, invalid configuration
    values, or misconfigured services.
    """
    pass


@dataclass
class ErrorResponse:
    """Standardized error response format for all agents and services.
    
    This class provides a consistent structure for error responses,
    making it easier to handle errors uniformly across the system.
    
    Attributes:
        error_type: The type/class of error that occurred
        message: Human-readable error message
        details: Additional context about the error (optional)
        retry_after: Suggested retry delay in seconds (optional)
    """
    
    error_type: str
    message: str
    details: Optional[Dict[str, Any]] = None
    retry_after: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error response to dictionary format."""
        result = {
            "error_type": self.error_type,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        return result
    
    def to_agent_response(self) -> Dict[str, Any]:
        """Convert to agent-compatible response format.
        
        Returns a dict with 'error' key for backward compatibility
        with existing agent message handlers.
        """
        return {
            "error": self.message,
            "error_type": self.error_type,
            "details": self.details,
            "retry_after": self.retry_after,
        }
    
    @classmethod
    def from_exception(cls, exc: Exception) -> "ErrorResponse":
        """Create ErrorResponse from any exception.
        
        Args:
            exc: The exception to convert
            
        Returns:
            ErrorResponse with appropriate fields populated
        """
        if isinstance(exc, AgentError):
            return exc.to_response()
        
        # For non-AgentError exceptions, create a generic response
        return cls(
            error_type=exc.__class__.__name__,
            message=str(exc),
            details={"original_exception": exc.__class__.__name__}
        )


def wrap_service_error(exc: Exception, context: str = "") -> AgentError:
    """Wrap a generic exception into an appropriate AgentError.
    
    This helper function converts common exception types into
    the appropriate AgentError subclass.
    
    Args:
        exc: The exception to wrap
        context: Additional context about where the error occurred
        
    Returns:
        An appropriate AgentError subclass instance
    """
    import httpx
    
    message = f"{context}: {str(exc)}" if context else str(exc)
    
    # HTTP-specific errors
    if isinstance(exc, httpx.TimeoutException):
        return TimeoutError(message, details={"exception_type": "TimeoutException"})
    
    if isinstance(exc, httpx.ConnectError):
        return ServiceUnavailableError(
            message,
            details={"exception_type": "ConnectError"},
            retry_after=5,
        )
    
    if isinstance(exc, httpx.HTTPStatusError):
        status_code = exc.response.status_code
        if status_code == 401 or status_code == 403:
            return AuthenticationError(
                message,
                details={"status_code": status_code}
            )
        elif status_code == 429:
            return ServiceUnavailableError(
                message,
                details={"status_code": status_code, "reason": "rate_limited"},
                retry_after=60,
            )
        elif status_code >= 500:
            return ServiceUnavailableError(
                message,
                details={"status_code": status_code},
                retry_after=10,
            )
        elif status_code >= 400:
            return InvalidParameterError(
                message,
                details={"status_code": status_code}
            )
    
    # Generic ValueError -> InvalidParameterError
    if isinstance(exc, ValueError):
        return InvalidParameterError(message)
    
    # Default: wrap as generic AgentError
    return AgentError(message, details={"original_type": exc.__class__.__name__})

