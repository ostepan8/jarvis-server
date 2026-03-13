"""
Tests for GoogleSearchService.

Tests verify:
1. Service initialization with/without credentials
2. Successful search with result parsing
3. Missing credentials handling
4. HTTP error handling (status errors, timeouts, generic errors)
5. Edge cases (empty results, malformed data, num_results clamping)
"""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from jarvis.services.search_service import GoogleSearchService


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
    logger = MagicMock()
    logger.log = MagicMock()
    return logger


@pytest.fixture
def search_service(mock_logger):
    """Create a GoogleSearchService with test credentials."""
    with patch.dict("os.environ", {"GOOGLE_SERVICE_ACCOUNT_FILE": ""}, clear=False):
        return GoogleSearchService(
            api_key="test-api-key",
            search_engine_id="test-engine-id",
            logger=mock_logger,
        )


@pytest.fixture
def search_service_no_creds(mock_logger):
    """Create a GoogleSearchService without credentials."""
    with patch.dict("os.environ", {}, clear=True):
        return GoogleSearchService(
            api_key=None,
            search_engine_id=None,
            logger=mock_logger,
        )


class TestGoogleSearchServiceInit:
    """Tests for GoogleSearchService initialization."""

    def test_init_with_explicit_credentials(self, mock_logger):
        """Test initialization with explicitly provided credentials."""
        with patch.dict("os.environ", {"GOOGLE_SERVICE_ACCOUNT_FILE": ""}, clear=False):
            service = GoogleSearchService(
                api_key="my-key",
                search_engine_id="my-engine",
                logger=mock_logger,
            )
        assert service.api_key == "my-key"
        assert service.search_engine_id == "my-engine"
        assert service.base_url == "https://www.googleapis.com/customsearch/v1"

    def test_init_with_env_vars(self, mock_logger):
        """Test initialization from environment variables."""
        with patch.dict(
            "os.environ",
            {
                "GOOGLE_SEARCH_API_KEY": "env-key",
                "GOOGLE_SEARCH_ENGINE_ID": "env-engine",
                "GOOGLE_SERVICE_ACCOUNT_FILE": "",
            },
        ):
            service = GoogleSearchService(logger=mock_logger)
            assert service.api_key == "env-key"
            assert service.search_engine_id == "env-engine"

    def test_init_without_credentials(self, mock_logger):
        """Test initialization without any credentials does not raise."""
        with patch.dict("os.environ", {}, clear=True):
            service = GoogleSearchService(
                api_key=None,
                search_engine_id=None,
                logger=mock_logger,
            )
            assert service.api_key is None
            assert service.search_engine_id is None

    def test_init_logs_credential_status(self, mock_logger):
        """Test that initialization logs whether credentials are present."""
        with patch.dict("os.environ", {"GOOGLE_SERVICE_ACCOUNT_FILE": ""}, clear=False):
            GoogleSearchService(
                api_key="key",
                search_engine_id="engine",
                logger=mock_logger,
            )
        mock_logger.log.assert_called_once_with(
            "INFO",
            "Google Search service initialized",
            {"auth_mode": "api_key", "has_search_engine_id": True},
        )


class TestGoogleSearchServiceSearch:
    """Tests for the search method."""

    @pytest.mark.asyncio
    async def test_search_success_with_results(self, search_service):
        """Test successful search returning results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Test Result 1",
                    "snippet": "This is snippet 1",
                    "link": "https://example.com/1",
                },
                {
                    "title": "Test Result 2",
                    "snippet": "This is snippet 2",
                    "link": "https://example.com/2",
                },
            ],
            "searchInformation": {"totalResults": "1500"},
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await search_service.search("test query", num_results=5)

        assert result["success"] is True
        assert len(result["results"]) == 2
        assert result["total_results"] == 1500
        assert result["error"] is None
        assert result["results"][0]["title"] == "Test Result 1"
        assert result["results"][0]["snippet"] == "This is snippet 1"
        assert result["results"][0]["link"] == "https://example.com/1"
        assert result["results"][1]["title"] == "Test Result 2"

    @pytest.mark.asyncio
    async def test_search_success_with_empty_results(self, search_service):
        """Test successful search with no results."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "searchInformation": {"totalResults": "0"},
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await search_service.search("obscure query")

        assert result["success"] is True
        assert result["results"] == []
        assert result["total_results"] == 0
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_search_missing_credentials(self, search_service_no_creds):
        """Test search fails gracefully when credentials are missing."""
        result = await search_service_no_creds.search("test query")

        assert result["success"] is False
        assert result["results"] == []
        assert result["total_results"] == 0
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_search_missing_api_key_only(self, mock_logger):
        """Test search fails when only api_key is missing."""
        with patch.dict("os.environ", {}, clear=True):
            service = GoogleSearchService(
                api_key=None,
                search_engine_id="engine-id",
                logger=mock_logger,
            )
        result = await service.search("test query")
        assert result["success"] is False
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_search_missing_search_engine_id_only(self, mock_logger):
        """Test search fails when only search_engine_id is missing."""
        with patch.dict("os.environ", {}, clear=True):
            service = GoogleSearchService(
                api_key="key",
                search_engine_id=None,
                logger=mock_logger,
            )
        result = await service.search("test query")
        assert result["success"] is False
        assert "not configured" in result["error"]

    @pytest.mark.asyncio
    async def test_search_num_results_clamped_to_10(self, search_service):
        """Test that num_results is clamped to maximum of 10."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "items": [],
            "searchInformation": {"totalResults": "0"},
        }

        captured_params = {}

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()

            async def capture_get(url, params=None, **kwargs):
                captured_params.update(params or {})
                return mock_response

            mock_client_instance.get = capture_get
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            await search_service.search("test", num_results=50)

        assert captured_params["num"] == 10

    @pytest.mark.asyncio
    async def test_search_http_status_error(self, search_service):
        """Test search handles HTTP status errors."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "403 Forbidden",
            request=MagicMock(),
            response=mock_response,
        )

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await search_service.search("test query")

        assert result["success"] is False
        assert result["results"] == []
        assert "403" in result["error"]

    @pytest.mark.asyncio
    async def test_search_timeout_error(self, search_service):
        """Test search handles timeout errors."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=httpx.TimeoutException("Connection timed out")
            )
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await search_service.search("test query")

        assert result["success"] is False
        assert result["results"] == []
        assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_search_generic_exception(self, search_service):
        """Test search handles generic exceptions."""
        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(
                side_effect=RuntimeError("Something went wrong")
            )
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await search_service.search("test query")

        assert result["success"] is False
        assert result["results"] == []
        assert "Something went wrong" in result["error"]

    @pytest.mark.asyncio
    async def test_search_result_with_missing_fields(self, search_service):
        """Test search handles results with missing fields gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "items": [
                {"title": "Only Title"},  # Missing snippet and link
                {},  # Completely empty item
            ],
            "searchInformation": {"totalResults": "2"},
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await search_service.search("test query")

        assert result["success"] is True
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "Only Title"
        assert result["results"][0]["snippet"] == ""
        assert result["results"][0]["link"] == ""
        assert result["results"][1]["title"] == ""

    @pytest.mark.asyncio
    async def test_search_missing_search_information(self, search_service):
        """Test search handles missing searchInformation field."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "items": [{"title": "Result", "snippet": "Snippet", "link": "https://x.com"}],
        }

        with patch("httpx.AsyncClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response)
            mock_client_instance.__aenter__ = AsyncMock(
                return_value=mock_client_instance
            )
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            result = await search_service.search("test query")

        assert result["success"] is True
        assert result["total_results"] == 0  # Defaults to 0 when missing
        assert len(result["results"]) == 1
