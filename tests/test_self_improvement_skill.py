"""Tests for the jarvis-self-improvement Claude Code skill.

Covers the shared HTTP client, argument parsing for each script,
and output formatting — all without touching a real server.
"""

import pytest
import json
import sys
import os
from unittest.mock import patch, MagicMock
import urllib.error

# Path to the skill scripts directory
SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills", "jarvis-self-improvement", "scripts",
)


def _fresh_client():
    """Import _client with a clean module cache."""
    if "_client" in sys.modules:
        del sys.modules["_client"]
    if SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, SCRIPTS_DIR)
    import _client
    return _client


def _mock_response(body: dict):
    """Create a mock urllib response that returns JSON."""
    mock = MagicMock()
    mock.read.return_value = json.dumps(body).encode("utf-8")
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


class TestClientBaseURL:
    """Tests for BASE_URL configuration."""

    def test_default_base_url(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JARVIS_API_URL", None)
            client = _fresh_client()
            assert client.BASE_URL == "http://localhost:8000/self-improvement"

    def test_custom_base_url(self):
        with patch.dict(os.environ, {"JARVIS_API_URL": "http://custom:9000/api"}):
            client = _fresh_client()
            assert client.BASE_URL == "http://custom:9000/api"


class TestClientGetRequest:
    """Tests for GET request handling."""

    def test_get_with_params_builds_url(self):
        client = _fresh_client()
        mock_resp = _mock_response({"ok": True})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            result = client.get("/discoveries", params={"type": "test_failure"})
            req = mock_open.call_args[0][0]
            assert "type=test_failure" in req.full_url
            assert result == {"ok": True}

    def test_get_without_params(self):
        client = _fresh_client()
        mock_resp = _mock_response({"running": False})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            result = client.get("/status")
            req = mock_open.call_args[0][0]
            assert req.full_url.endswith("/status")
            assert "?" not in req.full_url
            assert result == {"running": False}

    def test_get_filters_none_params(self):
        client = _fresh_client()
        mock_resp = _mock_response({"data": []})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            client.get("/discoveries", params={"type": "logs", "extra": None})
            req = mock_open.call_args[0][0]
            assert "type=logs" in req.full_url
            assert "extra" not in req.full_url


class TestClientPostRequest:
    """Tests for POST request handling."""

    def test_post_sends_json_body(self):
        client = _fresh_client()
        mock_resp = _mock_response({"status": "ok"})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            result = client.post("/discover", data={"lookback_hours": 48})
            req = mock_open.call_args[0][0]
            assert req.method == "POST"
            assert req.data == b'{"lookback_hours": 48}'
            assert result == {"status": "ok"}

    def test_post_without_data_sends_empty_object(self):
        client = _fresh_client()
        mock_resp = _mock_response({"status": "started"})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            client.post("/cycle")
            req = mock_open.call_args[0][0]
            assert req.data == b"{}"


class TestClientErrorHandling:
    """Tests for HTTP and connection error handling."""

    def test_http_error_exits(self):
        client = _fresh_client()
        error = urllib.error.HTTPError(
            "http://localhost:8000/self-improvement/status",
            500, "Internal Server Error", None, None,
        )

        with patch("_client.urllib.request.urlopen", side_effect=error):
            with pytest.raises(SystemExit):
                client.get("/status")

    def test_connection_error_exits(self):
        client = _fresh_client()
        error = urllib.error.URLError("Connection refused")

        with patch("_client.urllib.request.urlopen", side_effect=error):
            with pytest.raises(SystemExit):
                client.get("/status")


class TestDiscoverScript:
    """Tests for discover.py argument parsing and behaviour."""

    def test_discover_default_args(self):
        client = _fresh_client()
        mock_resp = _mock_response({"discoveries": [], "count": 0})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp):
            # Import the discover module
            if "discover" in sys.modules:
                del sys.modules["discover"]
            import discover

            with patch("sys.argv", ["discover.py"]):
                with patch("builtins.print") as mock_print:
                    discover.main()
                    output = json.loads(mock_print.call_args[0][0])
                    assert "discoveries" in output

    def test_discover_cached_flag(self):
        client = _fresh_client()
        mock_resp = _mock_response({"discoveries": [{"type": "todo"}]})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            if "discover" in sys.modules:
                del sys.modules["discover"]
            import discover

            with patch("sys.argv", ["discover.py", "--cached", "--type-filter", "todo"]):
                with patch("builtins.print"):
                    discover.main()
                    req = mock_open.call_args[0][0]
                    assert "type=todo" in req.full_url
                    assert req.method == "GET"


class TestGetStatusScript:
    """Tests for get_status.py."""

    def test_get_status_outputs_json(self):
        _fresh_client()
        mock_resp = _mock_response({"running": False, "discoveries_count": 0})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp):
            if "get_status" in sys.modules:
                del sys.modules["get_status"]
            import get_status

            with patch("sys.argv", ["get_status.py"]):
                with patch("builtins.print") as mock_print:
                    get_status.main()
                    output = json.loads(mock_print.call_args[0][0])
                    assert "running" in output


class TestSubmitTaskScript:
    """Tests for submit_task.py argument parsing."""

    def test_submit_task_sends_correct_payload(self):
        _fresh_client()
        mock_resp = _mock_response({"task_id": "abc-123"})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            if "submit_task" in sys.modules:
                del sys.modules["submit_task"]
            import submit_task

            with patch("sys.argv", [
                "submit_task.py",
                "--title", "Fix flaky test",
                "--description", "test_calendar times out",
                "--priority", "high",
                "--files", "tests/test_calendar_agent.py,jarvis/agents/calendar_agent/__init__.py",
            ]):
                with patch("builtins.print") as mock_print:
                    submit_task.main()
                    req = mock_open.call_args[0][0]
                    body = json.loads(req.data.decode("utf-8"))
                    assert body["title"] == "Fix flaky test"
                    assert body["priority"] == "high"
                    assert len(body["relevant_files"]) == 2


class TestGetReportScript:
    """Tests for get_report.py."""

    def test_get_latest_report(self):
        _fresh_client()
        mock_resp = _mock_response({"report": "all quiet"})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            if "get_report" in sys.modules:
                del sys.modules["get_report"]
            import get_report

            with patch("sys.argv", ["get_report.py"]):
                with patch("builtins.print"):
                    get_report.main()
                    req = mock_open.call_args[0][0]
                    assert req.full_url.endswith("/reports/latest")

    def test_get_all_reports_with_limit(self):
        _fresh_client()
        mock_resp = _mock_response({"reports": []})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp) as mock_open:
            if "get_report" in sys.modules:
                del sys.modules["get_report"]
            import get_report

            with patch("sys.argv", ["get_report.py", "--all", "--limit", "5"]):
                with patch("builtins.print"):
                    get_report.main()
                    req = mock_open.call_args[0][0]
                    assert "/reports" in req.full_url
                    assert "limit=5" in req.full_url


class TestGetContextScript:
    """Tests for get_context.py."""

    def test_get_context_raw_output(self):
        _fresh_client()
        mock_resp = _mock_response({"content": "print('hello')", "size": 15})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp):
            if "get_context" in sys.modules:
                del sys.modules["get_context"]
            import get_context

            with patch("sys.argv", ["get_context.py", "jarvis/core/system.py"]):
                with patch("builtins.print") as mock_print:
                    get_context.main()
                    # Raw mode prints content directly, not JSON
                    assert mock_print.call_args[0][0] == "print('hello')"

    def test_get_context_json_output(self):
        _fresh_client()
        mock_resp = _mock_response({"content": "x = 1", "size": 5})

        with patch("_client.urllib.request.urlopen", return_value=mock_resp):
            if "get_context" in sys.modules:
                del sys.modules["get_context"]
            import get_context

            with patch("sys.argv", ["get_context.py", "--json", "some/file.py"]):
                with patch("builtins.print") as mock_print:
                    get_context.main()
                    output = json.loads(mock_print.call_args[0][0])
                    assert output["content"] == "x = 1"
