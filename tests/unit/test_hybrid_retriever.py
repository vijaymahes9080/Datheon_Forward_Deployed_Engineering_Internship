"""Unit tests for BM25 lexical retrieval and Reciprocal Rank Fusion."""

from aegis.etl.vector_store import SearchResult
from aegis.rag.hybrid_retriever import BM25Retriever, HybridRetriever


def test_bm25_lexical_scoring():
    retriever = BM25Retriever()
    candidates = [
        SearchResult(
            chunk_id="c1",
            document_id="d1",
            text="Edge Gateway Appliance Gen4 model hardware SKU-INV-1001",
            score=0.5,
            tenant_id="t1",
            department="operations",
            access_tier=1,
            source_filename="catalog.csv",
            document_date="2026-01-01",
        ),
        SearchResult(
            chunk_id="c2",
            document_id="d2",
            text="Global Travel Policy economy flight class booking",
            score=0.4,
            tenant_id="t1",
            department="hr",
            access_tier=2,
            source_filename="policy.pdf",
            document_date="2026-01-01",
        ),
    ]

    scored = retriever.score_corpus("SKU-INV-1001", candidates)
    assert len(scored) == 2
    assert scored[0].chunk_id == "c1"
    assert scored[0].metadata["bm25_score"] > scored[1].metadata["bm25_score"]
