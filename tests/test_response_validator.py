"""Tests for jarvis.agents.response_validator — response validation utilities."""

import pytest
from unittest.mock import MagicMock

from jarvis.agents.response_validator import (
    ResponseValidationError,
    ensure_standard_format,
    get_validation_summary,
    validate_agent_response,
    validate_error_info,
)


# ---------------------------------------------------------------------------
# validate_agent_response
# ---------------------------------------------------------------------------
class TestValidateAgentResponse:
    """Tests for the validate_agent_response function."""

    def test_valid_minimal_response(self):
        resp = {"success": True, "response": "ok"}
        assert validate_agent_response(resp, "TestAgent") is True

    def test_valid_full_response(self):
        resp = {
            "success": True,
            "response": "done",
            "actions": [{"type": "create"}],
            "data": {"key": "val"},
            "metadata": {"agent": "test"},
            "error": None,
        }
        assert validate_agent_response(resp, "TestAgent") is True

    def test_missing_success_field(self):
        resp = {"response": "ok"}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_missing_response_field(self):
        resp = {"success": True}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_missing_both_required_fields(self):
        resp = {"data": {}}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_empty_dict(self):
        resp = {}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_success_wrong_type(self):
        resp = {"success": "yes", "response": "ok"}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_success_integer_type(self):
        resp = {"success": 1, "response": "ok"}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_response_wrong_type(self):
        resp = {"success": True, "response": 42}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_response_none_type(self):
        resp = {"success": True, "response": None}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_actions_wrong_type(self):
        resp = {"success": True, "response": "ok", "actions": "not a list"}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_actions_item_not_dict(self):
        resp = {"success": True, "response": "ok", "actions": ["string_action"]}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_actions_valid_list_of_dicts(self):
        resp = {"success": True, "response": "ok", "actions": [{"type": "x"}]}
        assert validate_agent_response(resp, "TestAgent") is True

    def test_actions_empty_list(self):
        resp = {"success": True, "response": "ok", "actions": []}
        assert validate_agent_response(resp, "TestAgent") is True

    def test_data_wrong_type(self):
        resp = {"success": True, "response": "ok", "data": "not a dict"}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_data_none_is_valid(self):
        resp = {"success": True, "response": "ok", "data": None}
        assert validate_agent_response(resp, "TestAgent") is True

    def test_metadata_wrong_type(self):
        resp = {"success": True, "response": "ok", "metadata": [1, 2, 3]}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_metadata_none_is_valid(self):
        resp = {"success": True, "response": "ok", "metadata": None}
        assert validate_agent_response(resp, "TestAgent") is True

    def test_error_wrong_type(self):
        resp = {"success": False, "response": "fail", "error": "not a dict"}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_error_none_is_valid(self):
        resp = {"success": False, "response": "fail", "error": None}
        assert validate_agent_response(resp, "TestAgent") is True

    def test_error_missing_message(self):
        resp = {"success": False, "response": "fail", "error": {"details": {}}}
        assert validate_agent_response(resp, "TestAgent") is False

    def test_error_valid_structure(self):
        resp = {
            "success": False,
            "response": "fail",
            "error": {"message": "something broke"},
        }
        assert validate_agent_response(resp, "TestAgent") is True

    def test_strict_mode_raises_on_failure(self):
        resp = {"data": {}}
        with pytest.raises(ResponseValidationError):
            validate_agent_response(resp, "TestAgent", strict=True)

    def test_strict_mode_passes_on_success(self):
        resp = {"success": True, "response": "ok"}
        assert validate_agent_response(resp, "TestAgent", strict=True) is True

    def test_logger_called_on_extra_fields(self):
        logger = MagicMock()
        resp = {"success": True, "response": "ok", "extra_field": "value"}
        validate_agent_response(resp, "TestAgent", logger=logger)
        logger.log.assert_called()

    def test_logger_called_on_validation_failure(self):
        logger = MagicMock()
        resp = {"data": {}}
        validate_agent_response(resp, "TestAgent", logger=logger)
        logger.log.assert_called()

    def test_no_extra_fields_no_logger_warning(self):
        logger = MagicMock()
        resp = {"success": True, "response": "ok"}
        validate_agent_response(resp, "TestAgent", logger=logger)
        logger.log.assert_not_called()

    def test_standard_fields_are_not_flagged(self):
        """All standard fields should not trigger extra field warning."""
        logger = MagicMock()
        resp = {
            "success": True,
            "response": "ok",
            "actions": [],
            "data": None,
            "metadata": None,
            "error": None,
        }
        validate_agent_response(resp, "TestAgent", logger=logger)
        # Logger should not be called since there are no issues
        logger.log.assert_not_called()


# ---------------------------------------------------------------------------
# validate_error_info
# ---------------------------------------------------------------------------
class TestValidateErrorInfo:
    """Tests for the validate_error_info function."""

    def test_valid_error_info(self):
        error = {"message": "something went wrong"}
        assert validate_error_info(error) == []

    def test_missing_message(self):
        error = {"details": {}}
        errors = validate_error_info(error)
        assert len(errors) == 1
        assert "message" in errors[0]

    def test_message_wrong_type(self):
        error = {"message": 42}
        errors = validate_error_info(error)
        assert len(errors) == 1
        assert "str" in errors[0]

    def test_valid_severity_warning(self):
        error = {"message": "msg", "severity": "warning"}
        assert validate_error_info(error) == []

    def test_valid_severity_error(self):
        error = {"message": "msg", "severity": "error"}
        assert validate_error_info(error) == []

    def test_valid_severity_critical(self):
        error = {"message": "msg", "severity": "critical"}
        assert validate_error_info(error) == []

    def test_invalid_severity(self):
        error = {"message": "msg", "severity": "info"}
        errors = validate_error_info(error)
        assert len(errors) == 1
        assert "severity" in errors[0]

    def test_details_valid_dict(self):
        error = {"message": "msg", "details": {"key": "val"}}
        assert validate_error_info(error) == []

    def test_details_none(self):
        error = {"message": "msg", "details": None}
        assert validate_error_info(error) == []

    def test_details_wrong_type(self):
        error = {"message": "msg", "details": "not a dict"}
        errors = validate_error_info(error)
        assert len(errors) == 1

    def test_retry_after_valid_int(self):
        error = {"message": "msg", "retry_after": 30}
        assert validate_error_info(error) == []

    def test_retry_after_valid_float(self):
        error = {"message": "msg", "retry_after": 30.5}
        assert validate_error_info(error) == []

    def test_retry_after_none(self):
        error = {"message": "msg", "retry_after": None}
        assert validate_error_info(error) == []

    def test_retry_after_wrong_type(self):
        error = {"message": "msg", "retry_after": "30"}
        errors = validate_error_info(error)
        assert len(errors) == 1

    def test_multiple_errors(self):
        error = {"severity": "bogus", "details": "not dict", "retry_after": "bad"}
        errors = validate_error_info(error)
        # Missing message + invalid severity + invalid details + invalid retry_after
        assert len(errors) >= 3


# ---------------------------------------------------------------------------
# ensure_standard_format
# ---------------------------------------------------------------------------
class TestEnsureStandardFormat:
    """Tests for the ensure_standard_format function."""

    def test_already_standard_format(self):
        resp = {"success": True, "response": "ok", "actions": []}
        result = ensure_standard_format(resp, "TestAgent")
        assert result is resp  # Same dict returned

    def test_legacy_format_with_response_key(self):
        resp = {"response": "hello", "actions": [{"type": "x"}]}
        result = ensure_standard_format(resp, "TestAgent")
        assert result["success"] is True
        assert result["response"] == "hello"
        assert result["actions"] == [{"type": "x"}]

    def test_legacy_format_with_error(self):
        resp = {"response": "fail", "error": "something broke"}
        result = ensure_standard_format(resp, "TestAgent")
        assert result["success"] is False
        assert result["error"]["message"] == "something broke"

    def test_legacy_format_no_error(self):
        resp = {"response": "ok"}
        result = ensure_standard_format(resp, "TestAgent")
        assert result["success"] is True
        assert result["error"] is None

    def test_legacy_result_format(self):
        resp = {"result": {"key": "value"}}
        result = ensure_standard_format(resp, "TestAgent")
        assert result["success"] is True
        assert result["data"] == {"key": "value"}

    def test_non_dict_string(self):
        result = ensure_standard_format("plain text", "TestAgent")
        assert result["success"] is True
        assert result["response"] == "plain text"

    def test_non_dict_number(self):
        result = ensure_standard_format(42, "TestAgent")
        assert result["success"] is True
        assert result["response"] == "42"

    def test_non_dict_none(self):
        result = ensure_standard_format(None, "TestAgent")
        assert result["success"] is True
        assert result["response"] == "None"

    def test_non_dict_list(self):
        result = ensure_standard_format([1, 2, 3], "TestAgent")
        assert result["success"] is True
        assert result["response"] == "[1, 2, 3]"

    def test_logger_warning_for_legacy_format(self):
        logger = MagicMock()
        resp = {"response": "ok"}
        ensure_standard_format(resp, "TestAgent", logger=logger)
        logger.log.assert_called()

    def test_logger_warning_for_result_format(self):
        logger = MagicMock()
        resp = {"result": "data"}
        ensure_standard_format(resp, "TestAgent", logger=logger)
        logger.log.assert_called()

    def test_logger_warning_for_non_dict(self):
        logger = MagicMock()
        ensure_standard_format("text", "TestAgent", logger=logger)
        logger.log.assert_called()

    def test_dict_without_response_or_result_or_success(self):
        """A dict without standard keys should be treated as non-dict fallback."""
        result = ensure_standard_format({"custom": "data"}, "TestAgent")
        assert result["success"] is True
        # Should be stringified since no known keys
        assert "custom" in result["response"]

    def test_legacy_format_preserves_data_and_metadata(self):
        resp = {
            "response": "ok",
            "data": {"key": "val"},
            "metadata": {"agent": "test"},
        }
        result = ensure_standard_format(resp, "TestAgent")
        assert result["data"] == {"key": "val"}
        assert result["metadata"] == {"agent": "test"}


# ---------------------------------------------------------------------------
# get_validation_summary
# ---------------------------------------------------------------------------
class TestGetValidationSummary:
    """Tests for the get_validation_summary function."""

    def test_empty_list(self):
        summary = get_validation_summary([])
        assert summary["total"] == 0
        assert summary["valid"] == 0
        assert summary["invalid"] == 0
        assert summary["validation_rate"] == 0

    def test_all_valid(self):
        responses = [
            {"success": True, "response": "ok"},
            {"success": False, "response": "fail"},
        ]
        summary = get_validation_summary(responses)
        assert summary["total"] == 2
        assert summary["valid"] == 2
        assert summary["invalid"] == 0
        assert summary["validation_rate"] == 1.0

    def test_all_invalid(self):
        responses = [
            {"data": {}},
            {"actions": []},
        ]
        summary = get_validation_summary(responses)
        assert summary["total"] == 2
        assert summary["valid"] == 0
        assert summary["invalid"] == 2
        assert summary["validation_rate"] == 0.0

    def test_mixed(self):
        responses = [
            {"success": True, "response": "ok"},
            {"data": {}},
            {"success": False, "response": "fail"},
        ]
        summary = get_validation_summary(responses)
        assert summary["total"] == 3
        assert summary["valid"] == 2
        assert summary["invalid"] == 1
        assert abs(summary["validation_rate"] - 2 / 3) < 0.001

    def test_missing_fields_tracked(self):
        responses = [
            {"success": True},  # missing "response"
        ]
        summary = get_validation_summary(responses)
        assert len(summary["missing_fields"]) == 1
        assert summary["missing_fields"][0] == (0, "response")

    def test_type_errors_tracked(self):
        responses = [
            {"success": "yes", "response": 42},
        ]
        summary = get_validation_summary(responses)
        assert len(summary["type_errors"]) == 2

    def test_single_valid_response(self):
        summary = get_validation_summary([{"success": True, "response": "ok"}])
        assert summary["total"] == 1
        assert summary["valid"] == 1
        assert summary["validation_rate"] == 1.0

    def test_summary_keys(self):
        summary = get_validation_summary([])
        expected_keys = {
            "total",
            "valid",
            "invalid",
            "validation_rate",
            "missing_fields",
            "type_errors",
        }
        assert set(summary.keys()) == expected_keys


# ---------------------------------------------------------------------------
# ResponseValidationError
# ---------------------------------------------------------------------------
class TestResponseValidationError:
    """Tests for the ResponseValidationError exception."""

    def test_is_exception(self):
        err = ResponseValidationError("bad response")
        assert isinstance(err, Exception)

    def test_message(self):
        err = ResponseValidationError("missing success field")
        assert str(err) == "missing success field"
