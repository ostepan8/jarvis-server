"""Tests for jarvis.core.constants — shared constants and enumerations."""

import pytest

from jarvis.core.constants import DEFAULT_PORT, LOG_DB_PATH, ExecutionResult


class TestDefaultConstants:
    """Tests for module-level constants."""

    def test_default_port_is_integer(self):
        assert isinstance(DEFAULT_PORT, int)

    def test_default_port_value(self):
        assert DEFAULT_PORT == 52718

    def test_log_db_path_is_string(self):
        assert isinstance(LOG_DB_PATH, str)

    def test_log_db_path_value(self):
        assert LOG_DB_PATH == "jarvis_logs.db"


class TestExecutionResult:
    """Tests for the ExecutionResult enum."""

    def test_success_value(self):
        assert ExecutionResult.SUCCESS == "success"
        assert ExecutionResult.SUCCESS.value == "success"

    def test_partial_value(self):
        assert ExecutionResult.PARTIAL == "partial"
        assert ExecutionResult.PARTIAL.value == "partial"

    def test_failure_value(self):
        assert ExecutionResult.FAILURE == "failure"
        assert ExecutionResult.FAILURE.value == "failure"

    def test_is_string_enum(self):
        assert isinstance(ExecutionResult.SUCCESS, str)
        assert isinstance(ExecutionResult.PARTIAL, str)
        assert isinstance(ExecutionResult.FAILURE, str)

    def test_enum_members_count(self):
        assert len(ExecutionResult) == 3

    def test_enum_from_value(self):
        assert ExecutionResult("success") == ExecutionResult.SUCCESS
        assert ExecutionResult("partial") == ExecutionResult.PARTIAL
        assert ExecutionResult("failure") == ExecutionResult.FAILURE

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            ExecutionResult("invalid")

    def test_enum_comparison_with_string(self):
        """ExecutionResult is a str enum, so it compares equal to its value."""
        assert ExecutionResult.SUCCESS == "success"
        assert ExecutionResult.FAILURE != "success"

    def test_enum_can_be_used_as_dict_key(self):
        d = {ExecutionResult.SUCCESS: 1, ExecutionResult.FAILURE: 0}
        assert d[ExecutionResult.SUCCESS] == 1

    def test_enum_iteration(self):
        members = list(ExecutionResult)
        assert ExecutionResult.SUCCESS in members
        assert ExecutionResult.PARTIAL in members
        assert ExecutionResult.FAILURE in members
