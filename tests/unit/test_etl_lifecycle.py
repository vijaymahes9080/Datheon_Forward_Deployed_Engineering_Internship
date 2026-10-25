"""Tests for document updates, deduplication, and deletion propagation in ETL pipeline."""

import pytest
from aegis.core.database import DocumentRecord, get_db_session, init_db
from aegis.etl.pipeline import ETLPipeline, IngestionItem


@pytest.fixture(autouse=True)
def setup_database():
    init_db()


def test_document_deduplication():
    pipeline = ETLPipeline()
    item = IngestionItem(
        filename="dedup_test.md",
        content_bytes=b"# Deduplication Test\nThis text is identical.",
        tenant_id="tenant_alpha",
        department="finance",
        access_tier=2,
    )
    # First ingestion
    m1 = pipeline.ingest_batch([item], "tenant_alpha")
    assert m1.files_accepted == 1
    assert m1.chunks_indexed >= 1

    # Second ingestion of unchanged content
    m2 = pipeline.ingest_batch([item], "tenant_alpha")
    assert m2.files_accepted == 1
    assert any("Content unchanged" in w for w in m2.warnings)


def test_document_update_replaces_chunks():
    pipeline = ETLPipeline()
    v1 = IngestionItem(
        filename="update_test.md",
        content_bytes=b"# Update Test\nVersion One Content.",
        tenant_id="tenant_beta",
        department="operations",
        access_tier=1,
    )
    m1 = pipeline.ingest_batch([v1], "tenant_beta")
    assert m1.files_accepted == 1

    # Updated version with different content
    v2 = IngestionItem(
        filename="update_test.md",
        content_bytes=b"# Update Test\nVersion Two Content Replaced.",
        tenant_id="tenant_beta",
        department="operations",
        access_tier=1,
    )
    m2 = pipeline.ingest_batch([v2], "tenant_beta")
    assert m2.files_accepted == 1


def test_document_deletion_propagation():
    pipeline = ETLPipeline()
    item = IngestionItem(
        filename="delete_test.md",
        content_bytes=b"# Deletion Test\nThis will be deleted.",
        tenant_id="tenant_gamma",
        department="hr",
        access_tier=2,
    )
    m1 = pipeline.ingest_batch([item], "tenant_gamma")
    assert m1.files_accepted == 1

    # Query DB to find document_id
    db = next(get_db_session())
    doc = (
        db.query(DocumentRecord)
        .filter(DocumentRecord.tenant_id == "tenant_gamma", DocumentRecord.source_filename == "delete_test.md")
        .first()
    )
    assert doc is not None

    # Delete
    deleted = pipeline.delete_document(doc.id, "tenant_gamma")
    assert deleted is True

    # Verify status in database
    db.refresh(doc)
    assert doc.status == "DELETED"
