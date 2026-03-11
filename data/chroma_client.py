"""
ChromaDB client singleton for per-project vector collections.

Each project gets its own named collection: project_{project_id}
Uses all-MiniLM-L6-v2 via chromadb's DefaultEmbeddingFunction (~90MB, auto-download on first use).
Persists to ./chroma_db/ alongside finance_agent.db.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

# Resolve chroma_db path relative to this file's directory (data/)
# so it lands in project root alongside finance_agent.db
_CHROMA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db")


class ProjectChromaClient:
    """Singleton ChromaDB client managing per-project collections."""

    _instance: Optional["ProjectChromaClient"] = None

    def __new__(cls) -> "ProjectChromaClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        import chromadb
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction  # type: ignore[import-untyped]

        os.makedirs(_CHROMA_DIR, exist_ok=True)
        self._client = chromadb.PersistentClient(path=_CHROMA_DIR)
        self._embedding_fn = DefaultEmbeddingFunction()
        self._initialized = True
        logger.info("ProjectChromaClient initialized at %s", _CHROMA_DIR)

    # ------------------------------------------------------------------
    # Collection helpers
    # ------------------------------------------------------------------

    def _collection_name(self, project_id: str) -> str:
        return f"project_{project_id}"

    def get_or_create_collection(self, project_id: str):
        """Return (or create) the named Chroma collection for a project."""
        self._ensure_initialized()
        return self._client.get_or_create_collection(
            name=self._collection_name(project_id),
            embedding_function=self._embedding_fn,
        )

    # ------------------------------------------------------------------
    # Document chunking and upsert
    # ------------------------------------------------------------------

    def add_document_chunks(
        self,
        project_id: str,
        document_id: str,
        filename: str,
        raw_text: str,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> List[str]:
        """
        Split raw_text into overlapping chunks, embed, and upsert into the collection.
        Returns list of chroma IDs for the inserted chunks.
        """
        self._ensure_initialized()
        chunks = self._split_text(raw_text, chunk_size, chunk_overlap)
        if not chunks:
            return []

        collection = self.get_or_create_collection(project_id)
        ids = [f"{document_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"source": filename, "document_id": document_id, "chunk_index": i} for i in range(len(chunks))]

        collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
        logger.info("Upserted %d chunks for document %s in project %s", len(chunks), document_id, project_id)
        return ids

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def query(
        self,
        project_id: str,
        query_text: str,
        n_results: int = 5,
    ) -> List[dict]:
        """
        Return top-n semantically relevant chunks for query_text.
        Each result: {"text": str, "source": str, "score": float}
        """
        self._ensure_initialized()
        collection = self.get_or_create_collection(project_id)

        # Chroma raises if collection is empty
        try:
            results = collection.query(query_texts=[query_text], n_results=n_results, include=["documents", "metadatas", "distances"])
        except Exception as exc:
            logger.warning("Chroma query failed for project %s: %s", project_id, exc)
            return []

        output: List[dict] = []
        docs = (results.get("documents") or [[]])[0]
        metas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        for doc, meta, dist in zip(docs, metas, distances):
            # Convert L2 distance to a similarity-like score in [0,1]
            score = 1.0 / (1.0 + dist) if dist is not None else 0.0
            output.append(
                {
                    "text": doc,
                    "source": meta.get("source", "") if meta else "",
                    "score": round(score, 4),
                }
            )
        return output

    # ------------------------------------------------------------------
    # Delete helpers
    # ------------------------------------------------------------------

    def delete_chunks(self, project_id: str, chroma_ids: List[str]) -> None:
        """Delete specific chunk IDs from a project's collection."""
        if not chroma_ids:
            return
        self._ensure_initialized()
        collection = self.get_or_create_collection(project_id)
        collection.delete(ids=chroma_ids)
        logger.info("Deleted %d chunks from project %s", len(chroma_ids), project_id)

    def delete_collection(self, project_id: str) -> None:
        """Drop the entire collection for a project."""
        self._ensure_initialized()
        name = self._collection_name(project_id)
        try:
            self._client.delete_collection(name=name)
            logger.info("Deleted Chroma collection %s", name)
        except Exception as exc:
            logger.warning("Failed to delete collection %s: %s", name, exc)

    # ------------------------------------------------------------------
    # Async wrappers
    # ------------------------------------------------------------------

    async def async_add_document_chunks(
        self,
        project_id: str,
        document_id: str,
        filename: str,
        raw_text: str,
        chunk_size: int = 800,
        chunk_overlap: int = 100,
    ) -> List[str]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.add_document_chunks(project_id, document_id, filename, raw_text, chunk_size, chunk_overlap),
        )

    async def async_query(
        self,
        project_id: str,
        query_text: str,
        n_results: int = 5,
    ) -> List[dict]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.query(project_id, query_text, n_results))

    async def async_delete_chunks(self, project_id: str, chroma_ids: List[str]) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self.delete_chunks(project_id, chroma_ids))

    async def async_delete_collection(self, project_id: str) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self.delete_collection(project_id))

    # ------------------------------------------------------------------
    # Internal text splitter
    # ------------------------------------------------------------------

    @staticmethod
    def _split_text(text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """Simple character-based splitter with overlap."""
        if not text:
            return []
        text = text.strip()
        if len(text) <= chunk_size:
            return [text]

        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            if end >= len(text):
                break
            start += chunk_size - chunk_overlap
        return chunks


# Module-level singleton accessor
def get_chroma_client() -> ProjectChromaClient:
    return ProjectChromaClient()
