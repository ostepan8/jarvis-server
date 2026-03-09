"""
Tests for VectorMemoryService and ModernOpenAIEmbeddingFunction.

Tests verify:
1. ModernOpenAIEmbeddingFunction initialization and calling
2. VectorMemoryService initialization (with/without API key)
3. add_memory (basic, with metadata, with user_id)
4. similarity_search (basic, with user_id, with metadata_filter)
5. query_memory (by id, by metadata, with user_id, with limit)
6. persist method
7. _get_user_collection
8. Edge cases (empty queries, None values)

All tests mock the ChromaDB and OpenAI clients to avoid external dependencies.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock


class TestModernOpenAIEmbeddingFunction:
    """Tests for ModernOpenAIEmbeddingFunction."""

    def test_init(self):
        """Test embedding function initialization."""
        with patch("jarvis.services.vector_memory.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            MockOpenAI.return_value = mock_client

            from jarvis.services.vector_memory import ModernOpenAIEmbeddingFunction

            ef = ModernOpenAIEmbeddingFunction(api_key="test-key")
            assert ef.model_name == "text-embedding-ada-002"
            MockOpenAI.assert_called_once_with(api_key="test-key")

    def test_init_custom_model(self):
        """Test embedding function with custom model name."""
        with patch("jarvis.services.vector_memory.OpenAI") as MockOpenAI:
            MockOpenAI.return_value = MagicMock()

            from jarvis.services.vector_memory import ModernOpenAIEmbeddingFunction

            ef = ModernOpenAIEmbeddingFunction(
                api_key="test-key", model_name="text-embedding-3-small"
            )
            assert ef.model_name == "text-embedding-3-small"

    def test_call_generates_embeddings(self):
        """Test that calling the function generates embeddings."""
        with patch("jarvis.services.vector_memory.OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_item1 = MagicMock()
            mock_item1.embedding = [0.1, 0.2, 0.3]
            mock_item2 = MagicMock()
            mock_item2.embedding = [0.4, 0.5, 0.6]
            mock_response.data = [mock_item1, mock_item2]
            mock_client.embeddings.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            from jarvis.services.vector_memory import ModernOpenAIEmbeddingFunction

            ef = ModernOpenAIEmbeddingFunction(api_key="test-key")
            result = ef(["hello", "world"])

            assert result == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
            mock_client.embeddings.create.assert_called_once_with(
                input=["hello", "world"], model="text-embedding-ada-002"
            )


class TestVectorMemoryServiceInit:
    """Tests for VectorMemoryService initialization."""

    def test_init_without_api_key_raises_value_error(self):
        """Test that initialization without an API key raises ValueError."""
        with patch.dict("os.environ", {}, clear=True):
            with patch("jarvis.services.vector_memory.chromadb") as mock_chromadb:
                mock_chromadb.PersistentClient = MagicMock
                with pytest.raises(ValueError, match="OpenAI API key is required"):
                    from jarvis.services.vector_memory import VectorMemoryService

                    VectorMemoryService(api_key=None)

    def test_init_with_explicit_api_key(self):
        """Test initialization with explicit API key."""
        with patch("jarvis.services.vector_memory.chromadb") as mock_chromadb:
            mock_client = MagicMock()
            mock_collection = MagicMock()
            mock_client.get_or_create_collection.return_value = mock_collection
            mock_chromadb.PersistentClient = MagicMock(return_value=mock_client)

            with patch("jarvis.services.vector_memory.OpenAI"):
                from jarvis.services.vector_memory import VectorMemoryService

                service = VectorMemoryService(api_key="test-key")
                assert service.collection == mock_collection

    def test_init_with_env_api_key(self):
        """Test initialization with API key from environment."""
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            with patch("jarvis.services.vector_memory.chromadb") as mock_chromadb:
                mock_client = MagicMock()
                mock_collection = MagicMock()
                mock_client.get_or_create_collection.return_value = mock_collection
                mock_chromadb.PersistentClient = MagicMock(return_value=mock_client)

                with patch("jarvis.services.vector_memory.OpenAI"):
                    from jarvis.services.vector_memory import VectorMemoryService

                    service = VectorMemoryService()
                    assert service.collection == mock_collection


def _create_mock_service():
    """Create a VectorMemoryService with all dependencies mocked.

    Returns a service with mock collection whose .add/.query/.get are
    plain functions (not MagicMock) to avoid Python 3.13's asyncio.to_thread
    InvalidSpecError when it tries to spec a Mock object.
    """
    with patch("jarvis.services.vector_memory.chromadb") as mock_chromadb:
        mock_client = MagicMock()
        mock_collection = MagicMock()
        # Give collection a real name attribute
        mock_collection.name = "jarvis_memory"
        mock_client.get_or_create_collection.return_value = mock_collection
        mock_chromadb.PersistentClient = MagicMock(return_value=mock_client)

        with patch("jarvis.services.vector_memory.OpenAI"):
            from jarvis.services.vector_memory import VectorMemoryService

            service = VectorMemoryService(api_key="test-key")
            service._mock_client = mock_client
            service._mock_collection = mock_collection
            return service


class TestAddMemory:
    """Tests for add_memory."""

    @pytest.mark.asyncio
    async def test_add_memory_basic(self):
        """Test adding a basic memory."""
        service = _create_mock_service()

        captured_calls = []

        def fake_add(ids, documents, metadatas):
            captured_calls.append({
                "ids": ids,
                "documents": documents,
                "metadatas": metadatas,
            })

        service.collection.add = fake_add

        memory_id = await service.add_memory("Hello world")

        assert memory_id is not None
        assert isinstance(memory_id, str)
        assert len(memory_id) > 0
        assert len(captured_calls) == 1
        assert captured_calls[0]["documents"] == ["Hello world"]
        assert captured_calls[0]["metadatas"] == [{}]

    @pytest.mark.asyncio
    async def test_add_memory_with_metadata(self):
        """Test adding a memory with metadata."""
        service = _create_mock_service()

        captured_calls = []

        def fake_add(ids, documents, metadatas):
            captured_calls.append({"metadatas": metadatas})

        service.collection.add = fake_add

        memory_id = await service.add_memory(
            "User likes pizza", metadata={"category": "preference"}
        )

        assert memory_id is not None
        assert captured_calls[0]["metadatas"] == [{"category": "preference"}]

    @pytest.mark.asyncio
    async def test_add_memory_with_user_id(self):
        """Test adding a memory with user_id adds it to metadata."""
        service = _create_mock_service()

        captured_calls = []

        def fake_add(ids, documents, metadatas):
            captured_calls.append({"metadatas": metadatas})

        service.collection.add = fake_add

        memory_id = await service.add_memory("User info", user_id=42)

        assert memory_id is not None
        assert captured_calls[0]["metadatas"] == [{"user_id": 42}]

    @pytest.mark.asyncio
    async def test_add_memory_generates_unique_ids(self):
        """Test that each memory gets a unique ID."""
        service = _create_mock_service()

        def fake_add(ids, documents, metadatas):
            pass

        service.collection.add = fake_add

        ids = set()
        for _ in range(10):
            memory_id = await service.add_memory("test")
            ids.add(memory_id)

        assert len(ids) == 10

    @pytest.mark.asyncio
    async def test_add_memory_with_user_id_and_metadata(self):
        """Test adding memory with both user_id and existing metadata."""
        service = _create_mock_service()

        captured_calls = []

        def fake_add(ids, documents, metadatas):
            captured_calls.append({"metadatas": metadatas})

        service.collection.add = fake_add

        await service.add_memory(
            "fact", metadata={"category": "pref"}, user_id=10
        )

        assert captured_calls[0]["metadatas"] == [
            {"category": "pref", "user_id": 10}
        ]


class TestSimilaritySearch:
    """Tests for similarity_search."""

    @pytest.mark.asyncio
    async def test_similarity_search_basic(self):
        """Test basic similarity search."""
        service = _create_mock_service()

        def fake_query(**kwargs):
            return {
                "documents": [["doc1", "doc2"]],
                "metadatas": [[{"key": "val1"}, {"key": "val2"}]],
            }

        service.collection.query = fake_query

        results = await service.similarity_search("test query", top_k=2)

        assert len(results) == 2
        assert results[0]["text"] == "doc1"
        assert results[0]["metadata"] == {"key": "val1"}
        assert results[1]["text"] == "doc2"

    @pytest.mark.asyncio
    async def test_similarity_search_with_user_id(self):
        """Test similarity search scoped to a user."""
        service = _create_mock_service()

        captured_kwargs = {}

        def fake_query(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "documents": [["user doc"]],
                "metadatas": [[{"user_id": 5}]],
            }

        # Mock user collection
        mock_user_collection = MagicMock()
        mock_user_collection.query = fake_query
        service._mock_client.get_or_create_collection.return_value = (
            mock_user_collection
        )

        results = await service.similarity_search("test", top_k=1, user_id=5)

        assert len(results) == 1
        assert results[0]["text"] == "user doc"
        assert captured_kwargs.get("where") == {"user_id": 5}

    @pytest.mark.asyncio
    async def test_similarity_search_with_metadata_filter(self):
        """Test similarity search with metadata filter."""
        service = _create_mock_service()

        captured_kwargs = {}

        def fake_query(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "documents": [["filtered doc"]],
                "metadatas": [[{"category": "pref"}]],
            }

        service.collection.query = fake_query

        results = await service.similarity_search(
            "test", metadata_filter={"category": "pref"}
        )

        assert len(results) == 1
        assert captured_kwargs.get("where") == {"category": "pref"}

    @pytest.mark.asyncio
    async def test_similarity_search_empty_results(self):
        """Test similarity search with no results."""
        service = _create_mock_service()

        def fake_query(**kwargs):
            return {"documents": [[]], "metadatas": [[]]}

        service.collection.query = fake_query

        results = await service.similarity_search("obscure query")
        assert results == []

    @pytest.mark.asyncio
    async def test_similarity_search_no_filter_no_where_clause(self):
        """Test that search without user_id or filter has no where clause."""
        service = _create_mock_service()

        captured_kwargs = {}

        def fake_query(**kwargs):
            captured_kwargs.update(kwargs)
            return {"documents": [[]], "metadatas": [[]]}

        service.collection.query = fake_query

        await service.similarity_search("test", top_k=3)

        assert "where" not in captured_kwargs
        assert captured_kwargs["n_results"] == 3


class TestQueryMemory:
    """Tests for query_memory."""

    @pytest.mark.asyncio
    async def test_query_memory_by_id(self):
        """Test querying memory by ID."""
        service = _create_mock_service()

        captured_kwargs = {}

        def fake_get(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "ids": ["id-123"],
                "documents": ["stored text"],
                "metadatas": [{"key": "val"}],
            }

        service.collection.get = fake_get

        results = await service.query_memory(memory_id="id-123")

        assert len(results) == 1
        assert results[0]["id"] == "id-123"
        assert results[0]["text"] == "stored text"
        assert results[0]["metadata"] == {"key": "val"}
        assert captured_kwargs["ids"] == ["id-123"]

    @pytest.mark.asyncio
    async def test_query_memory_by_metadata(self):
        """Test querying memory by metadata filter."""
        service = _create_mock_service()

        captured_kwargs = {}

        def fake_get(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "ids": ["id-1", "id-2"],
                "documents": ["doc1", "doc2"],
                "metadatas": [{"category": "pref"}, {"category": "pref"}],
            }

        service.collection.get = fake_get

        results = await service.query_memory(metadata={"category": "pref"})

        assert len(results) == 2
        assert captured_kwargs["where"] == {"category": "pref"}

    @pytest.mark.asyncio
    async def test_query_memory_with_user_id(self):
        """Test querying memory with user_id."""
        service = _create_mock_service()

        captured_kwargs = {}

        def fake_get(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "ids": ["id-1"],
                "documents": ["user doc"],
                "metadatas": [{"user_id": 42}],
            }

        mock_user_collection = MagicMock()
        mock_user_collection.get = fake_get
        service._mock_client.get_or_create_collection.return_value = (
            mock_user_collection
        )

        results = await service.query_memory(user_id=42)

        assert len(results) == 1
        assert captured_kwargs.get("where") == {"user_id": 42}

    @pytest.mark.asyncio
    async def test_query_memory_with_limit(self):
        """Test querying memory with limit."""
        service = _create_mock_service()

        captured_kwargs = {}

        def fake_get(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "ids": ["id-1"],
                "documents": ["doc1"],
                "metadatas": [{}],
            }

        service.collection.get = fake_get

        results = await service.query_memory(limit=1)

        assert len(results) == 1
        assert captured_kwargs.get("limit") == 1

    @pytest.mark.asyncio
    async def test_query_memory_empty_results(self):
        """Test querying memory with no results."""
        service = _create_mock_service()

        def fake_get(**kwargs):
            return {"ids": [], "documents": [], "metadatas": []}

        service.collection.get = fake_get

        results = await service.query_memory()
        assert results == []

    @pytest.mark.asyncio
    async def test_query_memory_with_metadata_and_user_id(self):
        """Test querying with both metadata and user_id."""
        service = _create_mock_service()

        captured_kwargs = {}

        def fake_get(**kwargs):
            captured_kwargs.update(kwargs)
            return {
                "ids": ["id-1"],
                "documents": ["doc1"],
                "metadatas": [{"category": "pref", "user_id": 5}],
            }

        mock_user_collection = MagicMock()
        mock_user_collection.get = fake_get
        service._mock_client.get_or_create_collection.return_value = (
            mock_user_collection
        )

        results = await service.query_memory(
            metadata={"category": "pref"}, user_id=5
        )

        assert len(results) == 1
        # The where clause should include both category and user_id
        where = captured_kwargs.get("where", {})
        assert where.get("category") == "pref"
        assert where.get("user_id") == 5

    @pytest.mark.asyncio
    async def test_query_memory_by_id_no_where(self):
        """Test that querying by ID only does not set a where clause."""
        service = _create_mock_service()

        captured_kwargs = {}

        def fake_get(**kwargs):
            captured_kwargs.update(kwargs)
            return {"ids": ["x"], "documents": ["d"], "metadatas": [{}]}

        service.collection.get = fake_get

        await service.query_memory(memory_id="x")
        assert "where" not in captured_kwargs


class TestPersist:
    """Tests for persist method."""

    @pytest.mark.asyncio
    async def test_persist_with_persist_method(self):
        """Test persist when client has persist method."""
        service = _create_mock_service()

        persist_called = []

        def fake_persist():
            persist_called.append(True)

        service.client.persist = fake_persist

        await service.persist()
        # persist is called via asyncio.to_thread, should have been called
        assert len(persist_called) == 1

    @pytest.mark.asyncio
    async def test_persist_without_persist_method(self):
        """Test persist when client does not have persist method."""
        service = _create_mock_service()
        # Remove persist attribute if it exists
        if hasattr(service.client, "persist"):
            delattr(service.client, "persist")

        # Should not raise
        await service.persist()

    @pytest.mark.asyncio
    async def test_persist_handles_exception_silently(self):
        """Test that persist handles exceptions without propagating."""
        service = _create_mock_service()

        def failing_persist():
            raise RuntimeError("persist failed")

        service.client.persist = failing_persist

        # Should not raise
        await service.persist()


class TestGetUserCollection:
    """Tests for _get_user_collection."""

    def test_get_user_collection_returns_collection(self):
        """Test that _get_user_collection returns a user-specific collection."""
        service = _create_mock_service()

        mock_user_collection = MagicMock()
        service._mock_client.get_or_create_collection.return_value = (
            mock_user_collection
        )

        result = service._get_user_collection(42)

        assert result == mock_user_collection
        service._mock_client.get_or_create_collection.assert_called_with(
            name="jarvis_memory_user_42",
            embedding_function=service.embedding_function,
        )

    def test_get_user_collection_different_users_produce_different_names(self):
        """Test that different user IDs produce different collection names."""
        service = _create_mock_service()

        service._get_user_collection(1)
        service._get_user_collection(2)

        calls = service._mock_client.get_or_create_collection.call_args_list
        names = [c.kwargs.get("name") for c in calls]
        assert "jarvis_memory_user_1" in names
        assert "jarvis_memory_user_2" in names
