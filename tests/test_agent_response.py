"""Tests for standardized agent response format."""

import pytest
from jarvis.agents.response import (
    AgentResponse,
    ErrorInfo,
    ErrorSeverity,
    merge_responses,
)


class TestErrorInfo:
    """Test ErrorInfo dataclass."""
    
    def test_create_error_info(self):
        """Test creating error info."""
        error = ErrorInfo(
            message="Test error",
            error_type="TestError",
            severity=ErrorSeverity.ERROR,
        )
        
        assert error.message == "Test error"
        assert error.error_type == "TestError"
        assert error.severity == ErrorSeverity.ERROR
    
    def test_error_info_to_dict(self):
        """Test converting error info to dict."""
        error = ErrorInfo(
            message="Test error",
            error_type="ValueError",
            details={"key": "value"},
            retry_after=5,
        )
        
        result = error.to_dict()
        
        assert result["message"] == "Test error"
        assert result["error_type"] == "ValueError"
        assert result["severity"] == "error"
        assert result["details"] == {"key": "value"}
        assert result["retry_after"] == 5
    
    def test_error_info_from_dict(self):
        """Test creating error info from dict."""
        data = {
            "message": "Test error",
            "error_type": "ValueError",
            "severity": "warning",
            "details": {"key": "value"},
        }
        
        error = ErrorInfo.from_dict(data)
        
        assert error.message == "Test error"
        assert error.error_type == "ValueError"
        assert error.severity == ErrorSeverity.WARNING
        assert error.details == {"key": "value"}
    
    def test_error_info_from_exception(self):
        """Test creating error info from exception."""
        exc = ValueError("Something went wrong")
        error = ErrorInfo.from_exception(exc)
        
        assert error.message == "Something went wrong"
        assert error.error_type == "ValueError"
        assert error.severity == ErrorSeverity.ERROR
        assert "exception_class" in error.details


class TestAgentResponse:
    """Test AgentResponse dataclass."""
    
    def test_create_success_response(self):
        """Test creating a success response."""
        response = AgentResponse(
            success=True,
            response="Task completed successfully",
            actions=[{"function": "test", "result": "ok"}],
        )
        
        assert response.success is True
        assert response.response == "Task completed successfully"
        assert len(response.actions) == 1
        assert response.error is None
    
    def test_create_error_response(self):
        """Test creating an error response."""
        error = ErrorInfo(message="Failed to process")
        response = AgentResponse(
            success=False,
            response="Unable to complete task",
            error=error,
        )
        
        assert response.success is False
        assert response.response == "Unable to complete task"
        assert response.error is not None
        assert response.error.message == "Failed to process"
    
    def test_to_dict(self):
        """Test converting response to dict."""
        response = AgentResponse(
            success=True,
            response="Done",
            actions=[{"function": "test"}],
            data={"result": 42},
            metadata={"time": 1.5},
        )
        
        result = response.to_dict()
        
        assert result["success"] is True
        assert result["response"] == "Done"
        assert result["actions"] == [{"function": "test"}]
        assert result["data"] == {"result": 42}
        assert result["metadata"] == {"time": 1.5}
        assert "error" not in result
    
    def test_to_dict_with_error(self):
        """Test converting error response to dict."""
        error = ErrorInfo(message="Test error")
        response = AgentResponse(
            success=False,
            response="Failed",
            error=error,
        )
        
        result = response.to_dict()
        
        assert result["success"] is False
        assert result["response"] == "Failed"
        assert "error" in result
        assert result["error"]["message"] == "Test error"
    
    def test_from_dict(self):
        """Test creating response from dict."""
        data = {
            "success": True,
            "response": "Test response",
            "actions": [{"function": "test"}],
            "data": {"key": "value"},
        }
        
        response = AgentResponse.from_dict(data)
        
        assert response.success is True
        assert response.response == "Test response"
        assert len(response.actions) == 1
        assert response.data == {"key": "value"}
    
    def test_from_dict_with_error(self):
        """Test creating error response from dict."""
        data = {
            "success": False,
            "response": "Failed",
            "error": {
                "message": "Error occurred",
                "error_type": "TestError",
            },
        }
        
        response = AgentResponse.from_dict(data)
        
        assert response.success is False
        assert response.error is not None
        assert response.error.message == "Error occurred"
        assert response.error.error_type == "TestError"
    
    def test_success_response_helper(self):
        """Test success_response helper method."""
        response = AgentResponse.success_response(
            response="Success",
            actions=[{"function": "test"}],
            data={"result": "ok"},
        )
        
        assert response.success is True
        assert response.response == "Success"
        assert response.error is None
    
    def test_error_response_helper(self):
        """Test error_response helper method."""
        error = ErrorInfo(message="Failed")
        response = AgentResponse.error_response(
            response="Operation failed",
            error=error,
        )
        
        assert response.success is False
        assert response.error is not None
        assert response.error.message == "Failed"
    
    def test_from_exception(self):
        """Test creating response from exception."""
        exc = ValueError("Invalid input")
        response = AgentResponse.from_exception(exc)
        
        assert response.success is False
        assert "Invalid input" in response.response
        assert response.error is not None
        assert response.error.error_type == "ValueError"
    
    def test_from_exception_with_custom_message(self):
        """Test creating response from exception with custom message."""
        exc = ValueError("Raw error")
        response = AgentResponse.from_exception(
            exc,
            user_message="Please try again later"
        )
        
        assert response.success is False
        assert response.response == "Please try again later"
        assert response.error.message == "Raw error"


class TestMergeResponses:
    """Test merging multiple agent responses."""
    
    def test_merge_empty_list(self):
        """Test merging empty response list."""
        result = merge_responses([])
        
        assert result.success is True
        assert result.response == "No responses to merge"
    
    def test_merge_single_response(self):
        """Test merging single response."""
        response = AgentResponse.success_response("Single response")
        result = merge_responses([response])
        
        assert result is response
    
    def test_merge_multiple_successes(self):
        """Test merging multiple successful responses."""
        responses = [
            AgentResponse.success_response("First", actions=[{"fn": "a"}]),
            AgentResponse.success_response("Second", actions=[{"fn": "b"}]),
            AgentResponse.success_response("Third", actions=[{"fn": "c"}]),
        ]
        
        result = merge_responses(responses)
        
        assert result.success is True
        assert "First" in result.response
        assert "Second" in result.response
        assert "Third" in result.response
        assert len(result.actions) == 3
    
    def test_merge_with_errors(self):
        """Test merging responses with errors."""
        responses = [
            AgentResponse.success_response("Success"),
            AgentResponse.error_response(
                "Failed",
                ErrorInfo(message="Error occurred")
            ),
        ]
        
        result = merge_responses(responses)
        
        # Overall success is False if any failed
        assert result.success is False
        assert result.error is not None
    
    def test_merge_data_fields(self):
        """Test merging data fields."""
        responses = [
            AgentResponse.success_response("A", data={"key1": "value1"}),
            AgentResponse.success_response("B", data={"key2": "value2"}),
        ]
        
        result = merge_responses(responses)
        
        assert result.data is not None
        assert "key1" in result.data
        assert "key2" in result.data
        assert result.data["key1"] == "value1"
        assert result.data["key2"] == "value2"


class TestResponseSerialization:
    """Test response serialization and deserialization."""
    
    def test_round_trip_success(self):
        """Test serializing and deserializing success response."""
        original = AgentResponse.success_response(
            response="Test",
            actions=[{"function": "test", "result": "ok"}],
            data={"key": "value"},
            metadata={"time": 1.5},
        )
        
        # Serialize to dict
        data = original.to_dict()
        
        # Deserialize back
        restored = AgentResponse.from_dict(data)
        
        assert restored.success == original.success
        assert restored.response == original.response
        assert restored.actions == original.actions
        assert restored.data == original.data
        assert restored.metadata == original.metadata
    
    def test_round_trip_error(self):
        """Test serializing and deserializing error response."""
        error = ErrorInfo(
            message="Test error",
            error_type="TestError",
            details={"context": "testing"},
        )
        original = AgentResponse.error_response(
            response="Failed",
            error=error,
            actions=[{"function": "attempt"}],
        )
        
        # Serialize to dict
        data = original.to_dict()
        
        # Deserialize back
        restored = AgentResponse.from_dict(data)
        
        assert restored.success == original.success
        assert restored.response == original.response
        assert restored.error.message == original.error.message
        assert restored.error.error_type == original.error.error_type
        assert restored.actions == original.actions


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

