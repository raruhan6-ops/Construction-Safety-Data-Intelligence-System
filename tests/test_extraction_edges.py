"""Extraction regression tests for raw values and malformed local tables."""

from pathlib import Path

import pytest

from csdis.database import connect
from csdis.ingestion import extract_csv_rows, extract_docx_tables, extract_html_tables, extract_xlsx_rows
from csdis.validation import detect_metric_conflicts


@pytest.fixture
def extraction_db(tmp_path: Path):
    connection = connect(tmp_path / "extraction.sqlite3")
    now = "2026-01-01T00:00:00+00:00"
    connection.execute(
        """INSERT INTO sources (source_id, publisher, title, source_type, canonical_url,
           format, authority_tier, created_at, updated_at)
           VALUES ('SRC-EDGE', 'Fixture', 'Extraction fixture', 'Dataset', 'local:test.csv',
           'CSV', 'Primary', ?, ?)""", (now, now)
    )
    version_id = "SRC-EDGE-v1"
    connection.execute(
        """INSERT INTO source_versions (source_version_id, source_id, version_label,
           original_filename, storage_path, sha256, file_size, content_type, retrieved_at,
           retrieval_method) VALUES (?, 'SRC-EDGE', 'fixture', 'fixture.csv', 'fixture.csv',
           'fixture-sha', 0, 'text/csv', ?, 'local fixture')""", (version_id, now)
    )
    connection.commit()
    yield connection, version_id
    connection.close()


def test_csv_extraction_preserves_blank_dash_footnote_and_leading_zero(tmp_path: Path, extraction_db):
    connection, version_id = extraction_db
    csv_path = tmp_path / "edge.csv"
    csv_path.write_text('label,value\nblank,\ndash,-\nfootnote,"24.3%1"\ncode,0012\n', encoding="utf-8")

    assert extract_csv_rows(csv_path, version_id, connection) == 5
    values = [row[0] for row in connection.execute(
        "SELECT raw_cells_json FROM extracted_table_rows ORDER BY row_index"
    )]
    assert values == [
        '["label", "value"]', '["blank", ""]', '["dash", "-"]',
        '["footnote", "24.3%1"]', '["code", "0012"]',
    ]


def test_malformed_html_rows_are_kept_as_raw_cells(tmp_path: Path, extraction_db):
    connection, version_id = extraction_db
    html_path = tmp_path / "malformed.html"
    html_path.write_text(
        "<table><tr><th>Year</th><th>Rate</th><th>Note</th></tr>"
        "<tr><td>2025</td><td>-</td></tr><tr><td>2026</td><td>4.8</td><td>provisional</td><td>extra</td></tr></table>",
        encoding="utf-8",
    )

    assert extract_html_tables(html_path, version_id, connection) == 3
    rows = [row[0] for row in connection.execute(
        "SELECT raw_cells_json FROM extracted_table_rows ORDER BY row_index"
    )]
    assert rows[1] == '["2025", "-"]'
    assert rows[2] == '["2026", "4.8", "provisional", "extra"]'


def test_xlsx_extraction_preserves_blank_dash_footnote_and_formula(tmp_path: Path, extraction_db):
    from openpyxl import Workbook

    connection, version_id = extraction_db
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Rates"
    sheet.append(["Label", "Value"])
    sheet.append(["Blank", None])
    sheet.append(["Dash", "-"])
    sheet.append(["Footnote", "12.5% a"])
    sheet.append(["Formula", "=1+1"])
    xlsx_path = tmp_path / "edge.xlsx"
    workbook.save(xlsx_path)

    assert extract_xlsx_rows(xlsx_path, version_id, connection) == 5
    rows = [row[0] for row in connection.execute(
        "SELECT raw_cells_json FROM extracted_table_rows ORDER BY row_index"
    )]
    assert rows == [
        '["Label", "Value"]', '["Blank", null]', '["Dash", "-"]',
        '["Footnote", "12.5% a"]', '["Formula", "=1+1"]',
    ]


def test_docx_extraction_preserves_empty_dash_and_footnote_cells(tmp_path: Path, extraction_db):
    from docx import Document

    connection, version_id = extraction_db
    document = Document()
    table = document.add_table(rows=4, cols=2)
    rows = (("Label", "Value"), ("Blank", ""), ("Dash", "-"), ("Footnote", "12.5% a"))
    for row, values in zip(table.rows, rows):
        for cell, value in zip(row.cells, values):
            cell.text = value
    docx_path = tmp_path / "edge.docx"
    document.save(docx_path)

    assert extract_docx_tables(docx_path, version_id, connection) == 4
    rows = [row[0] for row in connection.execute(
        "SELECT raw_cells_json FROM extracted_table_rows ORDER BY row_index"
    )]
    assert rows == [
        '["Label", "Value"]', '["Blank", ""]', '["Dash", "-"]',
        '["Footnote", "12.5% a"]',
    ]


def test_conflicts_do_not_cross_classification_dimensions(extraction_db):
    connection, version_id = extraction_db
    for evidence_id, locator in (("ev-rate", "rate row"), ("ev-agent", "agent row")):
        connection.execute(
            """INSERT INTO evidence (evidence_id, source_version_id, page_or_section,
               exact_quote_or_excerpt, locator_type, extraction_method, review_status,
               confidence, created_at) VALUES (?, ?, ?, 'value', 'table row', 'fixture',
               'Unreviewed', 'high', '2026-01-01T00:00:00+00:00')""",
            (evidence_id, version_id, locator),
        )
    for metric_id, evidence_id, dimension in (
        ("m-rate", "ev-rate", "Rate"), ("m-agent", "ev-agent", "Agent")
    ):
        connection.execute(
            """INSERT INTO metrics (metric_id, evidence_id, jurisdiction, sector_or_cohort,
               period_start, period_end, metric_label_raw, metric_label_harmonised,
               classification_dimension, denominator_definition, raw_value, numeric_value,
               unit, verification_status) VALUES (?, ?, 'Hong Kong', 'Public works contracts',
               '2025', '2025', 'Accident rate', 'accident rate', ?, 'per 1,000 workers',
               '4.8', 4.8, 'per 1,000 workers', 'Unverified')""",
            (metric_id, evidence_id, dimension),
        )

    assert detect_metric_conflicts(connection, "m-rate") == []
    assert connection.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0] == 0
