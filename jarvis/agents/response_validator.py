"""Response validation utilities for ensuring agent output consistency.

This module provides validation functions to check that agent responses
conform to the standardized format defined in response.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..logging import JarvisLogger


class ResponseValidationError(Exception):
    """Raised when a response fails validation."""
    pass


def validate_agent_response(
    response: Dict[str, Any],
    agent_name: str,
    logger: Optional["JarvisLogger"] = None,
    strict: bool = False,
) -> bool:
    """Validate that an agent response conforms to the standard format.
    
    Args:
        response: The response dictionary to validate
        agent_name: Name of the agent that produced the response
        logger: Optional logger for warning messages
        strict: If True, raise exception on validation failure
        
    Returns:
        True if valid, False if invalid (when strict=False)
        
    Raises:
        ResponseValidationError: If validation fails and strict=True
    """
    errors = []
    
    # Check required fields
    required_fields = ["success", "response"]
    for field in required_fields:
        if field not in response:
            errors.append(f"Missing required field: '{field}'")
    
    # Validate field types
    if "success" in response and not isinstance(response["success"], bool):
        errors.append(f"Field 'success' must be bool, got {type(response['success']).__name__}")
    
    if "response" in response and not isinstance(response["response"], str):
        errors.append(f"Field 'response' must be str, got {type(response['response']).__name__}")
    
    # Validate optional fields
    if "actions" in response:
        if not isinstance(response["actions"], list):
            errors.append(f"Field 'actions' must be list, got {type(response['actions']).__name__}")
        else:
            for i, action in enumerate(response["actions"]):
                if not isinstance(action, dict):
                    errors.append(f"actions[{i}] must be dict, got {type(action).__name__}")
    
    if "data" in response and response["data"] is not None:
        if not isinstance(response["data"], dict):
            errors.append(f"Field 'data' must be dict or None, got {type(response['data']).__name__}")
    
    if "metadata" in response and response["metadata"] is not None:
        if not isinstance(response["metadata"], dict):
            errors.append(f"Field 'metadata' must be dict or None, got {type(response['metadata']).__name__}")
    
    if "error" in response and response["error"] is not None:
        if not isinstance(response["error"], dict):
            errors.append(f"Field 'error' must be dict or None, got {type(response['error']).__name__}")
        else:
            # Validate error structure
            if "message" not in response["error"]:
                errors.append("error dict must contain 'message' field")
    
    # Check for deprecated/non-standard fields
    standard_fields = {"success", "response", "actions", "data", "metadata", "error"}
    extra_fields = set(response.keys()) - standard_fields
    if extra_fields and logger:
        logger.log(
            "WARNING",
            f"{agent_name} response contains non-standard fields",
            f"Fields: {', '.join(extra_fields)}",
        )
    
    # Report errors
    if errors:
        error_message = f"{agent_name} response validation failed: {'; '.join(errors)}"
        if logger:
            logger.log("WARNING", error_message, str(response))
        
        if strict:
            raise ResponseValidationError(error_message)
        
        return False
    
    return True


def validate_error_info(error: Dict[str, Any]) -> List[str]:
    """Validate error information structure.
    
    Args:
        error: Error dictionary to validate
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    if "message" not in error:
        errors.append("error must contain 'message' field")
    elif not isinstance(error["message"], str):
        errors.append(f"error.message must be str, got {type(error['message']).__name__}")
    
    if "severity" in error:
        valid_severities = ["warning", "error", "critical"]
        if error["severity"] not in valid_severities:
            errors.append(f"error.severity must be one of {valid_severities}, got {error['severity']}")
    
    if "details" in error and error["details"] is not None:
        if not isinstance(error["details"], dict):
            errors.append(f"error.details must be dict or None, got {type(error['details']).__name__}")
    
    if "retry_after" in error and error["retry_after"] is not None:
        if not isinstance(error["retry_after"], (int, float)):
            errors.append(f"error.retry_after must be number or None, got {type(error['retry_after']).__name__}")
    
    return errors


def ensure_standard_format(
    response: Any,
    agent_name: str,
    logger: Optional["JarvisLogger"] = None,
) -> Dict[str, Any]:
    """Ensure a response is in standard format, converting if necessary.
    
    This function attempts to convert legacy response formats to the
    standard format, logging warnings when conversions are necessary.
    
    Args:
        response: Response in any format
        agent_name: Name of the agent that produced the response
        logger: Optional logger for warning messages
        
    Returns:
        Response in standard format
    """
    # If already a dict with success field, validate and return
    if isinstance(response, dict) and "success" in response:
        validate_agent_response(response, agent_name, logger, strict=False)
        return response
    
    # Convert from legacy formats
    if isinstance(response, dict):
        # Legacy format: {"response": "...", "actions": [...]}
        if "response" in response:
            if logger:
                logger.log(
                    "WARNING",
                    f"{agent_name} returned legacy format (missing 'success' field)",
                    "Converting to standard format",
                )
            
            # Determine success based on presence of error
            has_error = "error" in response and response["error"]
            
            return {
                "success": not has_error,
                "response": response.get("response", ""),
                "actions": response.get("actions", []),
                "data": response.get("data"),
                "metadata": response.get("metadata"),
                "error": {"message": response["error"]} if has_error else None,
            }
        
        # Legacy format: {"result": {...}}
        if "result" in response:
            if logger:
                logger.log(
                    "WARNING",
                    f"{agent_name} returned legacy 'result' format",
                    "Converting to standard format",
                )
            
            return {
                "success": True,
                "response": str(response.get("result", "")),
                "data": response.get("result"),
            }
    
    # Fallback: treat entire response as text
    if logger:
        logger.log(
            "WARNING",
            f"{agent_name} returned non-dict response",
            f"Type: {type(response).__name__}, converting to standard format",
        )
    
    return {
        "success": True,
        "response": str(response),
    }


def get_validation_summary(responses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Get a summary of validation results for multiple responses.
    
    Useful for batch validation and reporting.
    
    Args:
        responses: List of response dictionaries to validate
        
    Returns:
        Dictionary with validation statistics
    """
    total = len(responses)
    valid = 0
    invalid = 0
    missing_fields = []
    type_errors = []
    
    for i, response in enumerate(responses):
        errors = []
        
        # Check required fields
        for field in ["success", "response"]:
            if field not in response:
                errors.append(f"Response {i}: missing '{field}'")
                missing_fields.append((i, field))
        
        # Check types
        if "success" in response and not isinstance(response["success"], bool):
            errors.append(f"Response {i}: 'success' wrong type")
            type_errors.append((i, "success"))
        
        if "response" in response and not isinstance(response["response"], str):
            errors.append(f"Response {i}: 'response' wrong type")
            type_errors.append((i, "response"))
        
        if errors:
            invalid += 1
        else:
            valid += 1
    
    return {
        "total": total,
        "valid": valid,
        "invalid": invalid,
        "validation_rate": valid / total if total > 0 else 0,
        "missing_fields": missing_fields,
        "type_errors": type_errors,
    }

