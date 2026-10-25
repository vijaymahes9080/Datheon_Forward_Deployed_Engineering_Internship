"""Vector Storage Interface and ChromaDB Cosine Implementation."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.config import Settings as ChromaSettings
from pydantic import BaseModel, Field

from aegis.core.config import get_settings
from aegis.etl.chunker import Chunk
from aegis.etl.embeddings import BaseEmbeddingProvider, get_embedding_provider


class SearchResult(BaseModel):
    """Normalized retrieval candidate returned from vector store."""
    chunk_id: str
    document_id: str
    text: str
    score: float  # Cosine similarity (1.0 is exact match)
    tenant_id: str
    department: str
    access_tier: int
    source_filename: str
    document_date: str
    page_number: Optional[int] = None
    row_identifier: Optional[str] = None
    section_heading: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseVectorStore(ABC):
    """Abstract interface for vector indexing and authorized retrieval."""

    @abstractmethod
    def index_chunks(self, chunks: List[Chunk]) -> int:
        """Index a batch of chunks with provenance metadata."""
        pass

    @abstractmethod
    def delete_document(self, document_id: str, tenant_id: str) -> int:
        """Delete all indexed chunks belonging to a document."""
        pass

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        tenant_id: str,
        allowed_departments: List[str],
        max_clearance: int,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """Perform authorized vector search enforcing tenant and ACL boundaries."""
        pass


class ChromaVectorStore(BaseVectorStore):
    """ChromaDB implementation with explicit cosine distance and ACL boundary filtering."""

    COLLECTION_NAME = "aegis_enterprise_knowledge"

    def __init__(
        self,
        persist_dir: Optional[str] = None,
        embedding_provider: Optional[BaseEmbeddingProvider] = None,
    ):
        settings = get_settings()
        self.persist_dir = persist_dir or settings.CHROMA_PERSIST_DIR
        self.client = chromadb.PersistentClient(path=self.persist_dir)
        self.embedding_provider = embedding_provider or get_embedding_provider()

        # Explicitly configure cosine similarity as mandated by specification
        self.collection = self.client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

    def index_chunks(self, chunks: List[Chunk]) -> int:
        if not chunks:
            return 0

        ids = [c.chunk_id for c in chunks]
        texts = [c.text for c in chunks]
        metadatas = [c.to_vector_metadata() for c in chunks]
        embeddings = self.embedding_provider.embed_batch(texts)

        # Upsert into ChromaDB
        self.collection.upsert(
            ids=ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings,
        )
        return len(chunks)

    def delete_document(self, document_id: str, tenant_id: str) -> int:
        """Purge all chunks matching document_id and tenant_id."""
        existing = self.collection.get(
            where={"$and": [{"document_id": document_id}, {"tenant_id": tenant_id}]}
        )
        if existing and existing["ids"]:
            self.collection.delete(ids=existing["ids"])
            return len(existing["ids"])
        return 0

    def search(
        self,
        query_vector: List[float],
        tenant_id: str,
        allowed_departments: List[str],
        max_clearance: int,
        top_k: int = 5,
        min_score: float = 0.0,
    ) -> List[SearchResult]:
        """Search ChromaDB with strict pre-retrieval ACL filtering.
        
        Zero-trust rule: Never return records outside tenant or exceeding clearance.
        """
        # Construct strict where clause
        where_clauses: List[Dict[str, Any]] = [
            {"tenant_id": {"$eq": tenant_id}},
            {"access_tier": {"$lte": max_clearance}},
        ]

        if allowed_departments:
            if len(allowed_departments) == 1:
                where_clauses.append({"department": {"$eq": allowed_departments[0]}})
            else:
                where_clauses.append({"department": {"$in": allowed_departments}})

        filter_condition = {"$and": where_clauses} if len(where_clauses) > 1 else where_clauses[0]

        query_res = self.collection.query(
            query_embeddings=[query_vector],
            n_results=top_k * 2,  # Fetch excess to filter and rank accurately
            where=filter_condition,
        )

        results: List[SearchResult] = []
        if not query_res or not query_res["ids"] or not query_res["ids"][0]:
            return results

        ids = query_res["ids"][0]
        documents = query_res["documents"][0]
        metadatas = query_res["metadatas"][0]
        distances = query_res["distances"][0] if "distances" in query_res and query_res["distances"] else [0.0] * len(ids)

        for i in range(len(ids)):
            dist = distances[i]
            # In Chroma cosine distance: cosine_distance = 1.0 - cosine_similarity
            similarity = max(0.0, 1.0 - dist)
            if similarity < min_score:
                continue

            meta = metadatas[i]
            page_num = meta.get("page_number", -1)
            results.append(
                SearchResult(
                    chunk_id=ids[i],
                    document_id=str(meta.get("document_id", "")),
                    text=documents[i],
                    score=float(similarity),
                    tenant_id=str(meta.get("tenant_id", "")),
                    department=str(meta.get("department", "")),
                    access_tier=int(meta.get("access_tier", 2)),
                    source_filename=str(meta.get("source_filename", "")),
                    document_date=str(meta.get("document_date", "")),
                    page_number=page_num if page_num != -1 else None,
                    row_identifier=meta.get("row_identifier") or None,
                    section_heading=meta.get("section_heading") or None,
                    metadata=meta,
                )
            )

        # Sort by similarity descending
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]


# Singleton instance
_vector_store: Optional[ChromaVectorStore] = None


def get_vector_store() -> ChromaVectorStore:
    """Get singleton Chroma vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = ChromaVectorStore()
    return _vector_store
