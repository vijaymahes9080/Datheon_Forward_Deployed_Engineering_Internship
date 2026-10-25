"""Unit tests for PDF, CSV, and Markdown document parsers."""

import io
import pytest
from reportlab.pdfgen import canvas

from aegis.etl.parsers.csv_parser import CSVDocumentParser
from aegis.etl.parsers.markdown_parser import MarkdownDocumentParser
from aegis.etl.parsers.pdf_parser import PDFDocumentParser


def test_pdf_parser_page_provenance_and_empty():
    parser = PDFDocumentParser()
    assert parser.can_parse("document.pdf")
    assert not parser.can_parse("document.docx")

    # Empty PDF handling
    empty_doc = parser.parse(b"", "empty.pdf", "tenant_a", "finance", 2)
    assert len(empty_doc.passages) == 0
    assert any("empty" in w.lower() for w in empty_doc.warnings)

    # Multi-page PDF
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(50, 750, "Quarterly Earnings Overview Page One")
    c.showPage()
    c.drawString(50, 750, "Segment Details Page Two")
    c.showPage()
    c.save()

    doc = parser.parse(buf.getvalue(), "report.pdf", "tenant_a", "finance", 3)
    assert len(doc.passages) == 2
    assert doc.passages[0].page_number == 1
    assert doc.passages[1].page_number == 2
    assert "Page One" in doc.passages[0].text
    assert "Page Two" in doc.passages[1].text


def test_csv_parser_row_identifier_and_headers():
    parser = CSVDocumentParser()
    assert parser.can_parse("inventory.csv")

    csv_data = (
        b"sku,item_name,quantity\n"
        b"SKU-01,Server Rack,12\n"
        b"SKU-02,Power Dist Unit,34\n"
    )

    doc = parser.parse(csv_data, "inventory.csv", "tenant_a", "operations", 1)
    assert len(doc.passages) == 2
    assert doc.passages[0].row_identifier == "row_1"
    assert doc.passages[1].row_identifier == "row_2"
    assert "sku: SKU-01" in doc.passages[0].text
    assert "quantity: 34" in doc.passages[1].text


def test_markdown_parser_hierarchical_breadcrumbs():
    parser = MarkdownDocumentParser()
    assert parser.can_parse("playbook.md")

    md_data = (
        b"# Incident Response\n"
        b"Overview text.\n\n"
        b"## Phase 1 Triage\n"
        b"Assess severity within 15 mins.\n\n"
        b"### Escalation\n"
        b"Page on-call director.\n"
    )

    doc = parser.parse(md_data, "playbook.md", "tenant_a", "security", 3)
    assert len(doc.passages) == 3
    assert doc.passages[0].section_heading == "# Incident Response"
    assert doc.passages[1].section_heading == "# Incident Response > ## Phase 1 Triage"
    assert doc.passages[2].section_heading == "# Incident Response > ## Phase 1 Triage > ### Escalation"
