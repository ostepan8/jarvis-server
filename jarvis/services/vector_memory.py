from __future__ import annotations

import os
import uuid
import asyncio
from typing import Any, Dict, List, Optional

from chromadb import Client
from chromadb.config import Settings
from chromadb.utils import embedding_functions


class VectorMemoryService:
    """Simple vector-based memory using ChromaDB."""

    def __init__(
        self,
        collection_name: str = "jarvis_memory",
        persist_directory: Optional[str] = None,
        embedding_model: str = "text-embedding-ada-002",
        api_key: Optional[str] = None,
    ) -> None:
        settings = Settings(chroma_db_impl="duckdb+parquet", persist_directory=persist_directory)
        self.client = Client(settings)
        self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=api_key or os.getenv("OPENAI_API_KEY"),
            model_name=embedding_model,
        )
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
        )

    async def persist(self) -> None:
        """Persist the underlying database to disk."""
        await asyncio.to_thread(self.client.persist)

    async def add_memory(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Store a piece of text in the vector database."""
        memory_id = str(uuid.uuid4())
        metadata = metadata or {}
        await asyncio.to_thread(
            self.collection.add, ids=[memory_id], documents=[text], metadatas=[metadata]
        )
        await asyncio.to_thread(self.client.persist)
        return memory_id

    async def similarity_search(self, text: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Retrieve top_k most similar memories to the given text."""
        result = await asyncio.to_thread(
            self.collection.query, query_texts=[text], n_results=top_k
        )
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        return [
            {"text": doc, "metadata": meta}
            for doc, meta in zip(docs, metas)
        ]
