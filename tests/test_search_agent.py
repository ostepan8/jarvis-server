"""Comprehensive tests for SearchAgent."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from jarvis.agents.search_agent import SearchAgent
from jarvis.agents.message import Message
from jarvis.services.search_service import GoogleSearchService
from jarvis.logging import JarvisLogger


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_search_message(prompt, num_results=5, from_agent="tester",
                         request_id="req-1"):
    """Build a capability_request Message for SearchAgent."""
    return Message(
        from_agent=from_agent,
        to_agent="SearchAgent",
        message_type="capability_request",
        content={
            "capability": "search",
            "data": {"prompt": prompt, "num_results": num_results},
        },
        request_id=request_id,
    )


def _make_mock_search_service():
    """Create a mock GoogleSearchService."""
    service = MagicMock(spec=GoogleSearchService)
    service.search = AsyncMock()
    return service


# ---------------------------------------------------------------------------
# Tests: metadata & properties
# ---------------------------------------------------------------------------

class TestSearchAgentProperties:
    """Test SearchAgent metadata and configuration."""

    def test_name(self):
        service = _make_mock_search_service()
        agent = SearchAgent(search_service=service)
        assert agent.name == "SearchAgent"

    def test_description(self):
        service = _make_mock_search_service()
        agent = SearchAgent(search_service=service)
        assert "search" in agent.description.lower()

    def test_capabilities(self):
        service = _make_mock_search_service()
        agent = SearchAgent(search_service=service)
        assert "search" in agent.capabilities

    def test_capabilities_returns_set(self):
        service = _make_mock_search_service()
        agent = SearchAgent(search_service=service)
        assert isinstance(agent.capabilities, set)


# ---------------------------------------------------------------------------
# Tests: _handle_capability_request with successful search
# ---------------------------------------------------------------------------

class TestSearchAgentSuccessfulSearch:
    """Test handling of successful search requests."""

    @pytest.mark.asyncio
    async def test_successful_search_with_results(self, monkeypatch):
        """A successful search returns formatted results."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [
                {"title": "Python Docs", "snippet": "Official Python documentation", "link": "https://python.org"},
                {"title": "Real Python", "snippet": "Python tutorials", "link": "https://realpython.com"},
                {"title": "PEP 8", "snippet": "Style guide for Python", "link": "https://pep8.org"},
            ],
            "total_results": 100,
        }
        agent = SearchAgent(search_service=service)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result
            captured["to"] = to

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("Python programming")
        await agent._handle_capability_request(msg)

        assert captured["result"]["success"] is True
        assert len(captured["result"]["results"]) == 3
        assert "Python Docs" in captured["result"]["response"]
        assert captured["to"] == "tester"

    @pytest.mark.asyncio
    async def test_successful_search_response_format(self, monkeypatch):
        """Search results include response text with titles and snippets."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [
                {"title": "Result 1", "snippet": "Snippet 1", "link": "https://example.com/1"},
            ],
            "total_results": 1,
        }
        agent = SearchAgent(search_service=service)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("test query")
        await agent._handle_capability_request(msg)

        response_text = captured["result"]["response"]
        assert "Result 1" in response_text
        assert "Snippet 1" in response_text

    @pytest.mark.asyncio
    async def test_search_with_more_total_results(self, monkeypatch):
        """When total_results > len(results), a count message is appended."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [
                {"title": "R1", "snippet": "S1", "link": "https://example.com"},
            ],
            "total_results": 1000,
        }
        agent = SearchAgent(search_service=service)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("broad query")
        await agent._handle_capability_request(msg)

        assert "1000" in captured["result"]["response"]

    @pytest.mark.asyncio
    async def test_search_passes_num_results(self, monkeypatch):
        """The num_results parameter is forwarded to the service."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [],
            "total_results": 0,
        }
        agent = SearchAgent(search_service=service)

        async def fake_send(to, result, request_id, msg_id):
            pass

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("test", num_results=3)
        await agent._handle_capability_request(msg)

        service.search.assert_called_once_with("test", 3)

    @pytest.mark.asyncio
    async def test_search_raw_results_included(self, monkeypatch):
        """Raw search results are included in the response payload."""
        service = _make_mock_search_service()
        results = [{"title": "T", "snippet": "S", "link": "L"}]
        service.search.return_value = {
            "success": True,
            "results": results,
            "total_results": 1,
        }
        agent = SearchAgent(search_service=service)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("test")
        await agent._handle_capability_request(msg)

        assert captured["result"]["raw_results"] == results


# ---------------------------------------------------------------------------
# Tests: empty and no results
# ---------------------------------------------------------------------------

class TestSearchAgentNoResults:
    """Test search with empty or no results."""

    @pytest.mark.asyncio
    async def test_search_no_results(self, monkeypatch):
        """Empty results list produces a 'no results' message."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [],
            "total_results": 0,
        }
        agent = SearchAgent(search_service=service)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("obscure query xyz")
        await agent._handle_capability_request(msg)

        assert "No results found" in captured["result"]["response"]

    @pytest.mark.asyncio
    async def test_search_result_with_title_only(self, monkeypatch):
        """Results with title but no snippet are still included."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [
                {"title": "Title Only", "snippet": "", "link": "https://example.com"},
            ],
            "total_results": 1,
        }
        agent = SearchAgent(search_service=service)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("test")
        await agent._handle_capability_request(msg)

        assert "Title Only" in captured["result"]["response"]


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------

class TestSearchAgentErrors:
    """Test error handling in SearchAgent."""

    @pytest.mark.asyncio
    async def test_empty_query_sends_error(self, monkeypatch):
        """An empty search query sends an error message."""
        service = _make_mock_search_service()
        agent = SearchAgent(search_service=service)
        errors = []

        async def fake_error(to, err, request_id):
            errors.append(err)

        monkeypatch.setattr(agent, "send_error", fake_error)
        msg = _make_search_message("")
        await agent._handle_capability_request(msg)

        assert len(errors) == 1
        assert "No search query" in errors[0]

    @pytest.mark.asyncio
    async def test_search_service_failure(self, monkeypatch):
        """When search service returns success=False, error is relayed."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": False,
            "results": [],
            "total_results": 0,
            "error": "API key invalid",
        }
        agent = SearchAgent(search_service=service)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("test query")
        await agent._handle_capability_request(msg)

        assert captured["result"]["success"] is False
        assert "API key invalid" in captured["result"]["error"]

    @pytest.mark.asyncio
    async def test_search_service_exception(self, monkeypatch):
        """An exception from search service sends an error message."""
        service = _make_mock_search_service()
        service.search.side_effect = ConnectionError("Network error")
        agent = SearchAgent(search_service=service)
        errors = []

        async def fake_error(to, err, request_id):
            errors.append(err)

        monkeypatch.setattr(agent, "send_error", fake_error)
        msg = _make_search_message("test query")
        await agent._handle_capability_request(msg)

        assert len(errors) == 1
        assert "Network error" in errors[0]

    @pytest.mark.asyncio
    async def test_non_search_capability_ignored(self, monkeypatch):
        """Non-search capabilities are silently ignored."""
        service = _make_mock_search_service()
        agent = SearchAgent(search_service=service)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["sent"] = True

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = Message(
            from_agent="tester",
            to_agent="SearchAgent",
            message_type="capability_request",
            content={"capability": "weather", "data": {"prompt": "test"}},
            request_id="req-1",
        )
        await agent._handle_capability_request(msg)
        assert "sent" not in captured


# ---------------------------------------------------------------------------
# Tests: _handle_capability_response
# ---------------------------------------------------------------------------

class TestSearchAgentCapabilityResponse:
    """Test capability response handler."""

    @pytest.mark.asyncio
    async def test_handle_capability_response_is_noop(self):
        """SearchAgent does not initiate requests, so this should be a no-op."""
        service = _make_mock_search_service()
        agent = SearchAgent(search_service=service)
        msg = Message(
            from_agent="other",
            to_agent="SearchAgent",
            message_type="capability_response",
            content={"data": "something"},
            request_id="req-1",
        )
        # Should not raise
        await agent._handle_capability_response(msg)


# ---------------------------------------------------------------------------
# Tests: edge cases
# ---------------------------------------------------------------------------

class TestSearchAgentEdgeCases:
    """Test edge cases for SearchAgent."""

    @pytest.mark.asyncio
    async def test_default_num_results(self, monkeypatch):
        """Default num_results is 5 when not specified."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [],
            "total_results": 0,
        }
        agent = SearchAgent(search_service=service)

        async def fake_send(to, result, request_id, msg_id):
            pass

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = Message(
            from_agent="tester",
            to_agent="SearchAgent",
            message_type="capability_request",
            content={"capability": "search", "data": {"prompt": "test"}},
            request_id="req-1",
        )
        await agent._handle_capability_request(msg)
        service.search.assert_called_once_with("test", 5)

    @pytest.mark.asyncio
    async def test_missing_data_defaults(self, monkeypatch):
        """Missing data dict defaults to empty values."""
        service = _make_mock_search_service()
        agent = SearchAgent(search_service=service)
        errors = []

        async def fake_error(to, err, request_id):
            errors.append(err)

        monkeypatch.setattr(agent, "send_error", fake_error)
        msg = Message(
            from_agent="tester",
            to_agent="SearchAgent",
            message_type="capability_request",
            content={"capability": "search"},
            request_id="req-1",
        )
        await agent._handle_capability_request(msg)
        # Empty prompt should trigger error
        assert len(errors) == 1

    @pytest.mark.asyncio
    async def test_search_service_returns_missing_error_key(self, monkeypatch):
        """When search fails without explicit error key, a default message is used."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": False,
            "results": [],
            "total_results": 0,
        }
        agent = SearchAgent(search_service=service)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("test")
        await agent._handle_capability_request(msg)

        assert captured["result"]["success"] is False
        assert "Search failed" in captured["result"]["response"]


# ---------------------------------------------------------------------------
# Tests: AI synthesis
# ---------------------------------------------------------------------------

class TestSearchAgentSynthesis:
    """Test AI synthesis of search results."""

    def _make_mock_ai_client(self, response_text="Synthesized answer."):
        """Create a mock AI client returning a configurable response."""
        ai_client = MagicMock()
        msg = MagicMock()
        msg.content = response_text
        ai_client.weak_chat = AsyncMock(return_value=(msg, None))
        return ai_client

    @pytest.mark.asyncio
    async def test_synthesizes_response_with_ai_client(self, monkeypatch):
        """When ai_client is present, results are synthesized into a natural answer."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [
                {"title": "Python Docs", "snippet": "Official docs", "link": "https://python.org"},
            ],
            "total_results": 1,
        }
        ai_client = self._make_mock_ai_client("Python is a programming language.")
        agent = SearchAgent(search_service=service, ai_client=ai_client)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("What is Python?")
        await agent._handle_capability_request(msg)

        assert captured["result"]["success"] is True
        assert captured["result"]["response"] == "Python is a programming language."
        ai_client.weak_chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_falls_back_to_raw_when_no_ai_client(self, monkeypatch):
        """Without ai_client, raw formatted results are returned."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [
                {"title": "Result Title", "snippet": "Result snippet", "link": "https://example.com"},
            ],
            "total_results": 1,
        }
        agent = SearchAgent(search_service=service, ai_client=None)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("test query")
        await agent._handle_capability_request(msg)

        assert captured["result"]["success"] is True
        assert "Result Title" in captured["result"]["response"]
        assert "Result snippet" in captured["result"]["response"]

    @pytest.mark.asyncio
    async def test_falls_back_on_synthesis_error(self, monkeypatch):
        """When AI synthesis raises an exception, falls back to raw results."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [
                {"title": "Fallback Title", "snippet": "Fallback snippet", "link": "https://example.com"},
            ],
            "total_results": 1,
        }
        ai_client = MagicMock()
        ai_client.weak_chat = AsyncMock(side_effect=RuntimeError("LLM down"))
        agent = SearchAgent(search_service=service, ai_client=ai_client)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("test query")
        await agent._handle_capability_request(msg)

        # Should fall back to raw formatting
        assert captured["result"]["success"] is True
        assert "Fallback Title" in captured["result"]["response"]

    @pytest.mark.asyncio
    async def test_weather_query_uses_search(self, monkeypatch):
        """Weather queries are handled through search capability."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [
                {"title": "Weather.com", "snippet": "72°F and sunny in Chicago", "link": "https://weather.com"},
            ],
            "total_results": 10,
        }
        ai_client = self._make_mock_ai_client("It's currently 72°F and sunny in Chicago.")
        agent = SearchAgent(search_service=service, ai_client=ai_client)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("What's the weather in Chicago?")
        await agent._handle_capability_request(msg)

        assert captured["result"]["success"] is True
        assert "72°F" in captured["result"]["response"]
        service.search.assert_called_once_with("What's the weather in Chicago?", 5)

    @pytest.mark.asyncio
    async def test_synthesis_with_empty_ai_response_falls_back(self, monkeypatch):
        """Empty AI response falls back to raw results."""
        service = _make_mock_search_service()
        service.search.return_value = {
            "success": True,
            "results": [
                {"title": "Raw Title", "snippet": "Raw snippet", "link": "https://example.com"},
            ],
            "total_results": 1,
        }
        ai_client = self._make_mock_ai_client("   ")  # Whitespace-only response
        agent = SearchAgent(search_service=service, ai_client=ai_client)
        captured = {}

        async def fake_send(to, result, request_id, msg_id):
            captured["result"] = result

        monkeypatch.setattr(agent, "send_capability_response", fake_send)
        msg = _make_search_message("test")
        await agent._handle_capability_request(msg)

        # Should fall back to raw formatting since AI response was empty
        assert "Raw Title" in captured["result"]["response"]
