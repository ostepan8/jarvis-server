"""Tests for jarvis.core.errors — exception hierarchy and error response utilities."""

import pytest

from jarvis.core.errors import (
    AgentError,
    AuthenticationError,
    CapabilityNotFoundError,
    ConfigurationError,
    ErrorResponse,
    InvalidParameterError,
    ProtocolExecutionError,
    ServiceUnavailableError,
    TimeoutError,
    wrap_service_error,
)


# ---------------------------------------------------------------------------
# AgentError base class
# ---------------------------------------------------------------------------
class TestAgentError:
    """Tests for the AgentError base exception."""

    def test_basic_construction(self):
        err = AgentError("something broke")
        assert str(err) == "something broke"
        assert err.message == "something broke"
        assert err.details == {}
        assert err.retry_after is None

    def test_construction_with_details_and_retry(self):
        details = {"key": "val"}
        err = AgentError("oops", details=details, retry_after=30)
        assert err.details == details
        assert err.retry_after == 30

    def test_details_defaults_to_empty_dict_when_none(self):
        err = AgentError("msg", details=None)
        assert err.details == {}

    def test_error_type_returns_class_name(self):
        err = AgentError("msg")
        assert err.error_type == "AgentError"

    def test_to_response_creates_error_response(self):
        err = AgentError("boom", details={"x": 1}, retry_after=10)
        resp = err.to_response()
        assert isinstance(resp, ErrorResponse)
        assert resp.error_type == "AgentError"
        assert resp.message == "boom"
        assert resp.details == {"x": 1}
        assert resp.retry_after == 10

    def test_is_exception(self):
        err = AgentError("test")
        assert isinstance(err, Exception)


# ---------------------------------------------------------------------------
# Subclass identity
# ---------------------------------------------------------------------------
class TestSubclassHierarchy:
    """All custom errors inherit from AgentError."""

    @pytest.mark.parametrize(
        "cls",
        [
            ServiceUnavailableError,
            InvalidParameterError,
            AuthenticationError,
            TimeoutError,
            ProtocolExecutionError,
            CapabilityNotFoundError,
            ConfigurationError,
        ],
    )
    def test_subclass_is_agent_error(self, cls):
        err = cls("test message")
        assert isinstance(err, AgentError)
        assert isinstance(err, Exception)

    @pytest.mark.parametrize(
        "cls,expected_name",
        [
            (ServiceUnavailableError, "ServiceUnavailableError"),
            (InvalidParameterError, "InvalidParameterError"),
            (AuthenticationError, "AuthenticationError"),
            (TimeoutError, "TimeoutError"),
            (ProtocolExecutionError, "ProtocolExecutionError"),
            (CapabilityNotFoundError, "CapabilityNotFoundError"),
            (ConfigurationError, "ConfigurationError"),
        ],
    )
    def test_error_type_matches_class_name(self, cls, expected_name):
        err = cls("msg")
        assert err.error_type == expected_name

    def test_subclass_preserves_details_and_retry(self):
        err = ServiceUnavailableError("down", details={"host": "x"}, retry_after=5)
        assert err.details == {"host": "x"}
        assert err.retry_after == 5

    def test_subclass_to_response(self):
        err = InvalidParameterError("bad param", details={"param": "foo"})
        resp = err.to_response()
        assert resp.error_type == "InvalidParameterError"
        assert resp.message == "bad param"


# ---------------------------------------------------------------------------
# ErrorResponse
# ---------------------------------------------------------------------------
class TestErrorResponse:
    """Tests for the ErrorResponse dataclass."""

    def test_basic_construction(self):
        resp = ErrorResponse(error_type="TestError", message="test")
        assert resp.error_type == "TestError"
        assert resp.message == "test"
        assert resp.details is None
        assert resp.retry_after is None

    def test_to_dict_minimal(self):
        resp = ErrorResponse(error_type="E", message="m")
        d = resp.to_dict()
        assert d == {"error_type": "E", "message": "m"}

    def test_to_dict_with_details_and_retry(self):
        resp = ErrorResponse(
            error_type="E", message="m", details={"a": 1}, retry_after=60
        )
        d = resp.to_dict()
        assert d["details"] == {"a": 1}
        assert d["retry_after"] == 60

    def test_to_dict_excludes_none_details(self):
        resp = ErrorResponse(error_type="E", message="m", details=None)
        d = resp.to_dict()
        assert "details" not in d

    def test_to_dict_excludes_none_retry_after(self):
        resp = ErrorResponse(error_type="E", message="m", retry_after=None)
        d = resp.to_dict()
        assert "retry_after" not in d

    def test_to_agent_response(self):
        resp = ErrorResponse(
            error_type="E", message="m", details={"a": 1}, retry_after=5
        )
        ar = resp.to_agent_response()
        assert ar["error"] == "m"
        assert ar["error_type"] == "E"
        assert ar["details"] == {"a": 1}
        assert ar["retry_after"] == 5

    def test_to_agent_response_none_fields(self):
        resp = ErrorResponse(error_type="E", message="m")
        ar = resp.to_agent_response()
        assert ar["details"] is None
        assert ar["retry_after"] is None

    def test_from_exception_with_agent_error(self):
        err = InvalidParameterError("bad", details={"p": 1}, retry_after=3)
        resp = ErrorResponse.from_exception(err)
        assert resp.error_type == "InvalidParameterError"
        assert resp.message == "bad"
        assert resp.details == {"p": 1}
        assert resp.retry_after == 3

    def test_from_exception_with_generic_exception(self):
        err = RuntimeError("generic")
        resp = ErrorResponse.from_exception(err)
        assert resp.error_type == "RuntimeError"
        assert resp.message == "generic"
        assert resp.details == {"original_exception": "RuntimeError"}
        assert resp.retry_after is None

    def test_from_exception_with_value_error(self):
        err = ValueError("bad value")
        resp = ErrorResponse.from_exception(err)
        assert resp.error_type == "ValueError"
        assert resp.message == "bad value"


# ---------------------------------------------------------------------------
# wrap_service_error
# ---------------------------------------------------------------------------
class TestWrapServiceError:
    """Tests for the wrap_service_error helper function."""

    def test_wraps_value_error_to_invalid_parameter(self):
        err = ValueError("bad")
        wrapped = wrap_service_error(err)
        assert isinstance(wrapped, InvalidParameterError)
        assert "bad" in wrapped.message

    def test_wraps_value_error_with_context(self):
        err = ValueError("bad")
        wrapped = wrap_service_error(err, context="during validation")
        assert "during validation" in wrapped.message
        assert "bad" in wrapped.message

    def test_wraps_unknown_exception_to_agent_error(self):
        err = KeyError("missing")
        wrapped = wrap_service_error(err)
        assert isinstance(wrapped, AgentError)
        assert wrapped.details.get("original_type") == "KeyError"

    def test_wraps_httpx_timeout(self):
        import httpx

        err = httpx.TimeoutException("timed out")
        wrapped = wrap_service_error(err)
        assert isinstance(wrapped, TimeoutError)
        assert wrapped.details.get("exception_type") == "TimeoutException"

    def test_wraps_httpx_connect_error(self):
        import httpx

        err = httpx.ConnectError("refused")
        wrapped = wrap_service_error(err)
        assert isinstance(wrapped, ServiceUnavailableError)
        assert wrapped.retry_after == 5

    def test_wraps_httpx_401_to_authentication_error(self):
        import httpx

        request = httpx.Request("GET", "http://example.com")
        response = httpx.Response(401, request=request)
        err = httpx.HTTPStatusError("unauthorized", request=request, response=response)
        wrapped = wrap_service_error(err)
        assert isinstance(wrapped, AuthenticationError)
        assert wrapped.details.get("status_code") == 401

    def test_wraps_httpx_403_to_authentication_error(self):
        import httpx

        request = httpx.Request("GET", "http://example.com")
        response = httpx.Response(403, request=request)
        err = httpx.HTTPStatusError("forbidden", request=request, response=response)
        wrapped = wrap_service_error(err)
        assert isinstance(wrapped, AuthenticationError)

    def test_wraps_httpx_429_to_service_unavailable(self):
        import httpx

        request = httpx.Request("GET", "http://example.com")
        response = httpx.Response(429, request=request)
        err = httpx.HTTPStatusError("rate limited", request=request, response=response)
        wrapped = wrap_service_error(err)
        assert isinstance(wrapped, ServiceUnavailableError)
        assert wrapped.retry_after == 60
        assert wrapped.details.get("reason") == "rate_limited"

    def test_wraps_httpx_500_to_service_unavailable(self):
        import httpx

        request = httpx.Request("GET", "http://example.com")
        response = httpx.Response(500, request=request)
        err = httpx.HTTPStatusError("server error", request=request, response=response)
        wrapped = wrap_service_error(err)
        assert isinstance(wrapped, ServiceUnavailableError)
        assert wrapped.retry_after == 10

    def test_wraps_httpx_400_to_invalid_parameter(self):
        import httpx

        request = httpx.Request("GET", "http://example.com")
        response = httpx.Response(400, request=request)
        err = httpx.HTTPStatusError("bad request", request=request, response=response)
        wrapped = wrap_service_error(err)
        assert isinstance(wrapped, InvalidParameterError)

    def test_context_prepended_to_message(self):
        err = RuntimeError("oops")
        wrapped = wrap_service_error(err, context="CalendarService")
        assert wrapped.message.startswith("CalendarService: ")

    def test_empty_context_no_prefix(self):
        err = RuntimeError("oops")
        wrapped = wrap_service_error(err, context="")
        assert wrapped.message == "oops"
