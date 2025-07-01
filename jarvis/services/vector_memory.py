from __future__ import annotations

import os
import uuid
import asyncio
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.utils import embedding_functions
from openai import OpenAI


class ModernOpenAIEmbeddingFunction:
    """Custom embedding function using modern OpenAI API."""

    def __init__(self, api_key: str, model_name: str = "text-embedding-ada-002"):
        self.client = OpenAI(api_key=api_key)
        self.model_name = model_name

    def __call__(self, input_texts: List[str]) -> List[List[float]]:
        """Generate embeddings for the input texts."""
        response = self.client.embeddings.create(
            input=input_texts, model=self.model_name
        )
        return [item.embedding for item in response.data]


class VectorMemoryService:
    """Simple vector-based memory using ChromaDB with modern OpenAI API."""

    def __init__(
        self,
        collection_name: str = "jarvis_memory",
        persist_directory: Optional[str] = None,
        embedding_model: str = "text-embedding-ada-002",
        api_key: Optional[str] = None,
    ) -> None:
        # Version-agnostic client creation
        persist_dir = persist_directory or "./chroma"

        if hasattr(chromadb, "PersistentClient"):
            self.client = chromadb.PersistentClient(path=persist_dir)
        else:
            try:
                self.client = chromadb.Client(
                    settings=chromadb.Settings(
                        persist_directory=persist_dir, is_persistent=True
                    )
                )
            except Exception:
                self.client = chromadb.Client(
                    settings=chromadb.config.Settings(
                        chroma_db_impl="duckdb+parquet",
                        persist_directory=persist_dir,
                    )
                )

        # Use custom embedding function with modern OpenAI API
        openai_api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OpenAI API key is required")

        self.embedding_function = ModernOpenAIEmbeddingFunction(
            api_key=openai_api_key, model_name=embedding_model
        )

        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
        )

    async def persist(self) -> None:
        """Persist the underlying database to disk."""
        try:
            if hasattr(self.client, "persist"):
                await asyncio.to_thread(self.client.persist)
        except Exception:
            pass

    async def add_memory(
        self, text: str, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Store a piece of text in the vector database."""
        memory_id = str(uuid.uuid4())
        metadata = metadata or {}
        await asyncio.to_thread(
            self.collection.add, ids=[memory_id], documents=[text], metadatas=[metadata]
        )
        return memory_id

    async def similarity_search(
        self, text: str, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """Retrieve top_k most similar memories to the given text."""
        result = await asyncio.to_thread(
            self.collection.query, query_texts=[text], n_results=top_k
        )
        docs = result.get("documents", [[]])[0]
        metas = result.get("metadatas", [[]])[0]
        return [{"text": doc, "metadata": meta} for doc, meta in zip(docs, metas)]
