"""Standardized response format for all agents.

This module defines the unified response schema that all agents should use
to ensure consistent output formatting and easy downstream processing.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from enum import Enum


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ErrorInfo:
    """Structured error information."""
    message: str
    error_type: Optional[str] = None
    severity: ErrorSeverity = ErrorSeverity.ERROR
    details: Optional[Dict[str, Any]] = None
    retry_after: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "message": self.message,
            "severity": self.severity.value,
        }
        if self.error_type:
            result["error_type"] = self.error_type
        if self.details:
            result["details"] = self.details
        if self.retry_after is not None:
            result["retry_after"] = self.retry_after
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ErrorInfo:
        """Create from dictionary."""
        severity = ErrorSeverity(data.get("severity", "error"))
        return cls(
            message=data["message"],
            error_type=data.get("error_type"),
            severity=severity,
            details=data.get("details"),
            retry_after=data.get("retry_after"),
        )
    
    @classmethod
    def from_exception(cls, exc: Exception, error_type: Optional[str] = None) -> ErrorInfo:
        """Create ErrorInfo from an exception."""
        return cls(
            message=str(exc),
            error_type=error_type or exc.__class__.__name__,
            severity=ErrorSeverity.ERROR,
            details={"exception_class": exc.__class__.__name__},
        )


@dataclass
class AgentResponse:
    """Standardized response format for all agents.
    
    All agents should return responses in this format to ensure consistent
    output rendering and downstream processing.
    
    Attributes:
        success: Whether the operation succeeded
        response: Natural language response for the user
        actions: List of actions taken (tool calls, API calls, etc.)
        data: Structured data returned by the agent (optional)
        metadata: Agent-specific metadata (optional)
        error: Structured error information (optional)
    
    Examples:
        Successful response:
        >>> response = AgentResponse(
        ...     success=True,
        ...     response="I've added the meeting to your calendar.",
        ...     actions=[{"function": "create_event", "result": {...}}]
        ... )
        
        Error response:
        >>> response = AgentResponse(
        ...     success=False,
        ...     response="Unable to add the event due to a conflict.",
        ...     error=ErrorInfo(message="Calendar conflict detected")
        ... )
    """
    
    # Required fields
    success: bool
    response: str
    
    # Optional fields
    actions: List[Dict[str, Any]] = field(default_factory=list)
    data: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[ErrorInfo] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.
        
        Returns a dictionary with only non-None values for cleaner JSON output.
        """
        result = {
            "success": self.success,
            "response": self.response,
        }
        
        if self.actions:
            result["actions"] = self.actions
        
        if self.data is not None:
            result["data"] = self.data
        
        if self.metadata is not None:
            result["metadata"] = self.metadata
        
        if self.error is not None:
            result["error"] = self.error.to_dict()
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AgentResponse:
        """Create AgentResponse from dictionary.
        
        Args:
            data: Dictionary containing response data
            
        Returns:
            AgentResponse instance
        """
        error_data = data.get("error")
        error = ErrorInfo.from_dict(error_data) if error_data else None
        
        return cls(
            success=data.get("success", True),
            response=data.get("response", ""),
            actions=data.get("actions", []),
            data=data.get("data"),
            metadata=data.get("metadata"),
            error=error,
        )
    
    @classmethod
    def success_response(
        cls,
        response: str,
        actions: Optional[List[Dict[str, Any]]] = None,
        data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> AgentResponse:
        """Create a successful response.
        
        Convenience method for creating success responses.
        """
        return cls(
            success=True,
            response=response,
            actions=actions or [],
            data=data,
            metadata=metadata,
            error=None,
        )
    
    @classmethod
    def error_response(
        cls,
        response: str,
        error: ErrorInfo,
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentResponse:
        """Create an error response.
        
        Convenience method for creating error responses.
        """
        return cls(
            success=False,
            response=response,
            actions=actions or [],
            data=None,
            metadata=None,
            error=error,
        )
    
    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        user_message: Optional[str] = None,
        actions: Optional[List[Dict[str, Any]]] = None,
    ) -> AgentResponse:
        """Create an error response from an exception.
        
        Args:
            exc: The exception that occurred
            user_message: Optional user-friendly message (defaults to exception message)
            actions: Optional list of actions taken before the error
            
        Returns:
            AgentResponse with error information
        """
        error = ErrorInfo.from_exception(exc)
        message = user_message or f"An error occurred: {str(exc)}"
        
        return cls.error_response(
            response=message,
            error=error,
            actions=actions,
        )


def merge_responses(responses: List[AgentResponse]) -> AgentResponse:
    """Merge multiple agent responses into a single response.
    
    Useful for aggregating responses from multiple agents handling
    different parts of a request.
    
    Args:
        responses: List of AgentResponse objects to merge
        
    Returns:
        Merged AgentResponse
    """
    if not responses:
        return AgentResponse.success_response("No responses to merge")
    
    if len(responses) == 1:
        return responses[0]
    
    # Determine overall success (all must succeed)
    overall_success = all(r.success for r in responses)
    
    # Merge response texts
    response_texts = [r.response for r in responses if r.response]
    merged_response = " ".join(response_texts)
    
    # Merge actions
    merged_actions = []
    for r in responses:
        merged_actions.extend(r.actions)
    
    # Merge data
    merged_data = {}
    for r in responses:
        if r.data:
            merged_data.update(r.data)
    
    # Collect errors
    errors = [r.error for r in responses if r.error]
    error = errors[0] if errors else None
    
    return AgentResponse(
        success=overall_success,
        response=merged_response,
        actions=merged_actions,
        data=merged_data if merged_data else None,
        metadata={"merged_from": len(responses)},
        error=error,
    )

