"""Error transformation middleware for the agent network.

This module provides utilities to transform exceptions into standardized
error responses throughout the agent communication system.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING
import traceback

from .errors import (
    AgentError,
    ErrorResponse,
    wrap_service_error,
)

if TYPE_CHECKING:
    from ..logging import JarvisLogger


class ErrorMiddleware:
    """Middleware for transforming exceptions into standardized error responses.
    
    This class provides methods to catch and transform exceptions during
    agent message handling, ensuring all errors are reported in a consistent
    format throughout the system.
    """
    
    def __init__(self, logger: Optional["JarvisLogger"] = None):
        """Initialize error middleware.
        
        Args:
            logger: Optional logger for recording error transformations
        """
        self.logger = logger
    
    def transform_exception(
        self,
        exc: Exception,
        context: str = "",
        include_traceback: bool = False,
    ) -> ErrorResponse:
        """Transform any exception into a standardized ErrorResponse.
        
        Args:
            exc: The exception to transform
            context: Additional context about where the error occurred
            include_traceback: Whether to include stack trace in details
            
        Returns:
            ErrorResponse with standardized format
        """
        # Log the error if logger is available
        if self.logger:
            error_context = f"{context}: {exc}" if context else str(exc)
            self.logger.log(
                "ERROR",
                "Error middleware caught exception",
                {
                    "exception_type": exc.__class__.__name__,
                    "message": str(exc),
                    "context": context,
                }
            )
        
        # If it's already an AgentError, convert directly
        if isinstance(exc, AgentError):
            response = exc.to_response()
        else:
            # Wrap generic exceptions
            agent_error = wrap_service_error(exc, context)
            response = agent_error.to_response()
        
        # Add traceback if requested (useful for debugging)
        if include_traceback and self.logger:
            response.details = response.details or {}
            response.details["traceback"] = traceback.format_exc()
        
        return response
    
    def error_to_message_content(
        self,
        exc: Exception,
        context: str = "",
    ) -> Dict[str, Any]:
        """Convert exception to message content for agent communication.
        
        This creates a dict suitable for inclusion in a Message object's
        content field, maintaining backward compatibility with existing
        error message handling.
        
        Args:
            exc: The exception to convert
            context: Additional context about where the error occurred
            
        Returns:
            Dict with error information in agent-compatible format
        """
        response = self.transform_exception(exc, context)
        return response.to_agent_response()
    
    def wrap_capability_execution(
        self,
        func: callable,
        *args: Any,
        context: str = "",
        **kwargs: Any,
    ) -> tuple[Any, Optional[ErrorResponse]]:
        """Wrap a capability execution with error handling.
        
        This method executes a function and catches any exceptions,
        transforming them into standardized error responses.
        
        Args:
            func: The function to execute
            *args: Positional arguments for the function
            context: Context about what's being executed
            **kwargs: Keyword arguments for the function
            
        Returns:
            Tuple of (result, error_response). If successful, error_response
            is None. If an error occurred, result is None and error_response
            contains the error details.
        """
        try:
            result = func(*args, **kwargs)
            return result, None
        except Exception as exc:
            error_response = self.transform_exception(exc, context)
            return None, error_response
    
    async def wrap_capability_execution_async(
        self,
        func: callable,
        *args: Any,
        context: str = "",
        **kwargs: Any,
    ) -> tuple[Any, Optional[ErrorResponse]]:
        """Async version of wrap_capability_execution.
        
        Args:
            func: The async function to execute
            *args: Positional arguments for the function
            context: Context about what's being executed
            **kwargs: Keyword arguments for the function
            
        Returns:
            Tuple of (result, error_response). If successful, error_response
            is None. If an error occurred, result is None and error_response
            contains the error details.
        """
        try:
            result = await func(*args, **kwargs)
            return result, None
        except Exception as exc:
            error_response = self.transform_exception(exc, context)
            return None, error_response


def create_error_response_dict(
    message: str,
    error_type: str = "AgentError",
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Utility function to create a standardized error response dict.
    
    This is a convenience function for creating error responses without
    needing to instantiate the full middleware or exception classes.
    
    Args:
        message: The error message
        error_type: The type/class of error
        details: Additional error details
        
    Returns:
        Dict with standardized error format
    """
    response = ErrorResponse(
        error_type=error_type,
        message=message,
        details=details,
    )
    return response.to_agent_response()

