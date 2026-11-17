"""Text extraction helpers for researcher-reviewed document ingestion."""

from __future__ import annotations

import hashlib
import csv
import hashlib
import json
import sqlite3
import re
from typing import Any
from pathlib import Path

from csdis.database import audit, now_iso


def extract_pdf_evidence(pdf_path: Path, source_version_id: str, connection: sqlite3.Connection) -> tuple[int, int]:
    """Extract native PDF text page by page and create provisional evidence rows.

    Returns (pages_with_text, pages_without_text). Scanned pages are left empty;
    OCR is intentionally not run automatically.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF extraction needs pypdf. Install project dependencies with pip install -r requirements.txt.") from exc

    reader = PdfReader(str(pdf_path))
    with connection:
        pages_with_text = 0
        pages_without_text = 0
        for page_index, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if not text:
                pages_without_text += 1
                continue
            pages_with_text += 1
            evidence_id = "ev-" + hashlib.sha256(f"{source_version_id}:{page_index}".encode()).hexdigest()[:20]
            exists = connection.execute("SELECT 1 FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
            if exists:
                continue
            connection.execute(
                """INSERT INTO evidence (evidence_id, source_version_id, page_or_section,
                   exact_quote_or_excerpt, locator_type, extraction_method, review_status,
                   reviewer, confidence, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, 'PDF page', 'Native text', 'Unreviewed', NULL, 'medium', ?, ?)""",
                (evidence_id, source_version_id, f"PDF page {page_index}", text,
                 json.dumps({"page_number": page_index, "text_length": len(text)}, ensure_ascii=False), now_iso()),
            )
        audit(connection, "pdf_text_extracted", "source_version", source_version_id,
              {"pages_with_text": pages_with_text, "pages_without_text": pages_without_text})
    return pages_with_text, pages_without_text


def extract_html_evidence(html_path: Path, source_version_id: str, connection: sqlite3.Connection) -> int:
    """Extract visible HTML text, including dense semantic content containers."""
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("HTML extraction needs beautifulsoup4. Install project dependencies with pip install -r requirements.txt.") from exc

    raw_html = html_path.read_bytes()
    soup = BeautifulSoup(raw_html, "html.parser")
    structured_metadata: list[tuple[str, str]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or script.get_text())
        except (TypeError, json.JSONDecodeError):
            continue

        def collect_metadata(value: Any) -> None:
            if isinstance(value, dict):
                for key in ("headline", "description"):
                    text = value.get(key)
                    if isinstance(text, str) and len(text.strip()) >= 20:
                        normalized = " ".join(text.split())
                        if all(existing_text != normalized for _, existing_text in structured_metadata):
                            structured_metadata.append((key, normalized))
                for nested_value in value.values():
                    if isinstance(nested_value, (dict, list)):
                        collect_metadata(nested_value)
            elif isinstance(value, list):
                for nested_value in value:
                    collect_metadata(nested_value)

        collect_metadata(payload)
    for hidden in soup(["script", "style", "noscript", "svg"]):
        hidden.decompose()
    document_title = soup.title.get_text(" ", strip=True) if soup.title else "Untitled HTML source"
    headings: list[str] = []
    count = 0
    text_elements = list(soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]))
    standard_text_length = sum(len(" ".join(node.get_text(" ", strip=True).split())) for node in text_elements)
    body = soup.body
    body_text = " ".join(body.get_text(" ", strip=True).split()) if body else ""
    content_containers = []
    if body_text and standard_text_length < len(body_text) * 0.6:
        semantic_pattern = re.compile(r"main|content|article|press.?release|release.?body", re.IGNORECASE)
        for container in soup.find_all(["main", "article", "div"]):
            identifier = str(container.get("id") or "")
            classes = " ".join(container.get("class") or [])
            if not semantic_pattern.search(f"{identifier} {classes}"):
                continue
            # Prefer the innermost semantic container so wrappers do not
            # create several copies of the same long passage.
            nested = container.find(["main", "article", "div"], attrs={"id": semantic_pattern})
            if nested:
                continue
            excerpt_length = len(" ".join(container.get_text(" ", strip=True).split()))
            structured_length = sum(
                len(" ".join(node.get_text(" ", strip=True).split()))
                for node in container.find_all(["h1", "h2", "h3", "h4", "p", "li"])
            )
            if excerpt_length >= 500 and structured_length < excerpt_length * 0.6:
                content_containers.append(container)
    text_elements.extend(content_containers)
    with connection:
        for element_index, element in enumerate(text_elements, start=1):
            text = " ".join(element.get_text(" ", strip=True).split())
            if not text:
                continue
            tag_name = element.name or "text"
            if tag_name.startswith("h"):
                headings.append(text)
            section = " > ".join(headings[-3:]) or document_title
            excerpt = f"{text}"
            evidence_id = "ev-" + hashlib.sha256(
                f"{source_version_id}:html:{element_index}:{excerpt}".encode("utf-8")
            ).hexdigest()[:20]
            is_main_content = any(element is container for container in content_containers)
            existing = connection.execute(
                "SELECT locator_type FROM evidence WHERE evidence_id=?", (evidence_id,)
            ).fetchone()
            if existing:
                if is_main_content:
                    connection.execute(
                        """UPDATE evidence SET page_or_section=?, exact_quote_or_excerpt=?,
                           locator_type='HTML main content', metadata_json=? WHERE evidence_id=?""",
                        (f"{document_title} — {section} ({tag_name} #{element_index})", excerpt,
                         json.dumps({"document_title": document_title, "tag": tag_name,
                                     "element_index": element_index, "heading_path": headings[-3:]}, ensure_ascii=False),
                         evidence_id),
                    )
                continue
            connection.execute(
                """INSERT INTO evidence (evidence_id, source_version_id, page_or_section,
                   exact_quote_or_excerpt, locator_type, extraction_method, review_status,
                   reviewer, confidence, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, ?, 'HTML parser', 'Unreviewed',
                   NULL, 'medium', ?, ?)""",
                (evidence_id, source_version_id, f"{document_title} — {section} ({tag_name} #{element_index})",
                 excerpt, "HTML main content" if is_main_content else "HTML heading/paragraph",
                 json.dumps({"document_title": document_title, "tag": tag_name,
                                     "element_index": element_index, "heading_path": headings[-3:]}, ensure_ascii=False),
                 now_iso()),
            )
            count += 1
        for metadata_index, (key, excerpt) in enumerate(structured_metadata, start=1):
            evidence_id = "ev-" + hashlib.sha256(
                f"{source_version_id}:jsonld:{metadata_index}:{key}:{excerpt}".encode("utf-8")
            ).hexdigest()[:20]
            if connection.execute("SELECT 1 FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone():
                continue
            connection.execute(
                """INSERT INTO evidence (evidence_id, source_version_id, page_or_section,
                   exact_quote_or_excerpt, locator_type, extraction_method, review_status,
                   reviewer, confidence, metadata_json, created_at)
                   VALUES (?, ?, ?, ?, 'HTML structured metadata', 'JSON-LD parser',
                   'Unreviewed', NULL, 'medium', ?, ?)""",
                (evidence_id, source_version_id, f"{document_title} (JSON-LD {key})", excerpt,
                 json.dumps({"document_title": document_title, "metadata_key": key,
                             "metadata_index": metadata_index}, ensure_ascii=False), now_iso()),
            )
            count += 1
        audit(connection, "html_text_extracted", "source_version", source_version_id,
              {"new_evidence_records": count, "document_title": document_title,
               "main_content_containers": len(content_containers),
               "jsonld_items": len(structured_metadata)})
    return count


def extract_html_tables(html_path: Path, source_version_id: str, connection: sqlite3.Connection) -> int:
    """Extract HTML table cells as candidate rows with stable table/row locators."""
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("HTML table extraction needs beautifulsoup4.") from exc

    soup = BeautifulSoup(html_path.read_bytes(), "html.parser")
    inserted = 0
    with connection:
        for table_index, table in enumerate(soup.find_all("table")):
            for row_index, tr in enumerate(table.find_all("tr")):
                cells = [" ".join(cell.get_text(" ", strip=True).split())
                         for cell in tr.find_all(["th", "td"], recursive=False)]
                if not cells:
                    continue
                inserted += _store_candidate_row(
                    connection, source_version_id, f"html-table:{table_index}:{row_index}", 0,
                    table_index, row_index, f"HTML table {table_index + 1}, row {row_index + 1}",
                    cells, "HTML table parser",
                )
        audit(connection, "html_tables_extracted", "source_version", source_version_id,
              {"new_candidate_rows": inserted, "tables": len(soup.find_all("table"))})
    return inserted


def extract_devb_live_rates(html_path: Path, source_version_id: str, connection: sqlite3.Connection) -> int:
    """Create provisional metrics from DEVB's annual historical rate table."""
    from decimal import Decimal, InvalidOperation
    from csdis.validation import detect_metric_conflicts

    soup = None
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_path.read_bytes(), "html.parser")
    except ImportError as exc:
        raise RuntimeError("DEVB live table extraction needs beautifulsoup4.") from exc

    inserted = 0
    with connection:
        for table_index, table in enumerate(soup.find_all("table")):
            rows = []
            for tr in table.find_all("tr"):
                cells = [" ".join(cell.get_text(" ", strip=True).split())
                         for cell in tr.find_all(["th", "td"], recursive=False)]
                if cells:
                    rows.append(cells)
            header_index = next((i for i, row in enumerate(rows)
                                 if row and row[0].strip().casefold() == "year"), None)
            if header_index is None or header_index + 1 >= len(rows):
                continue
            header = rows[header_index]
            rate_row_index = next((i for i, row in enumerate(rows)
                                   if row and row[0].strip().casefold() == "accident rate"), None)
            if rate_row_index is None:
                continue
            rate_row = rows[rate_row_index]
            for column, year_text in enumerate(header[1:], start=1):
                if not re.fullmatch(r"20\d{2}", year_text.strip()) or column >= len(rate_row):
                    continue
                year = year_text.strip()
                raw_value = rate_row[column]
                try:
                    numeric_value = float(Decimal(raw_value.strip()))
                except (InvalidOperation, AttributeError):
                    numeric_value = None
                source_row = connection.execute(
                    """SELECT evidence_id FROM extracted_table_rows WHERE source_version_id=?
                       AND page_number=0 AND table_index=? AND row_index=?""",
                    (source_version_id, table_index, rate_row_index),
                ).fetchone()
                if source_row is None:
                    continue
                evidence_id = source_row["evidence_id"]
                metric_id = "metric-" + hashlib.sha256(
                    f"{evidence_id}:annual-rate:{year}".encode()
                ).hexdigest()[:20]
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO metrics (metric_id, evidence_id, jurisdiction,
                       sector_or_cohort, period_start, period_end, metric_label_raw,
                       metric_label_harmonised, classification_dimension, denominator_definition,
                       raw_value, numeric_value, unit, rate_multiplier, verification_status)
                       VALUES (?, ?, 'Hong Kong', 'Public works contracts', ?, ?, 'Accident Rate',
                       'Reportable accident rate per 1,000 workers per year', 'Rate',
                       'per 1,000 workers per year', ?, ?, 'accidents per 1,000 workers per year',
                       1000, 'Unverified')""",
                    (metric_id, evidence_id, year, year, raw_value, numeric_value),
                )
                if cursor.rowcount:
                    inserted += 1
                # Re-run comparison on existing rows too. A prior extraction
                # may have created the metric before its comparator existed.
                detect_metric_conflicts(connection, metric_id)
        # Preserve monthly rolling averages as their own reporting periods.
        # These are distinct from the annual historical summary below.
        month_numbers = {name: number for number, name in enumerate(
            ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"), 1)}
        for table_index in range(3):
            table_rows = connection.execute(
                """SELECT row_index, raw_cells_json, evidence_id FROM extracted_table_rows
                   WHERE source_version_id=? AND page_number=0 AND table_index=?
                   ORDER BY row_index""", (source_version_id, table_index)
            ).fetchall()
            row_map = {row["row_index"]: row for row in table_rows}
            year_row = row_map.get(0)
            month_row = row_map.get(1)
            rolling_row = next((row for row in table_rows
                                if json.loads(row["raw_cells_json"])[0].strip().casefold()
                                == "rolling 12 month average"), None)
            if not year_row or not month_row or not rolling_row:
                continue
            year_cells = json.loads(year_row["raw_cells_json"])
            month_cells = json.loads(month_row["raw_cells_json"])
            value_cells = json.loads(rolling_row["raw_cells_json"])
            if not year_cells or not re.fullmatch(r"20\d{2}", str(year_cells[0]).strip()):
                continue
            year = str(year_cells[0]).strip()
            for column, month_name in enumerate(month_cells[1:], start=1):
                month = month_numbers.get(str(month_name).strip().upper())
                if month is None or column >= len(value_cells):
                    continue
                raw_value = str(value_cells[column] or "").strip()
                if not raw_value:
                    continue
                try:
                    numeric_value = float(Decimal(raw_value))
                except (InvalidOperation, ValueError):
                    numeric_value = None
                period = f"{year}-{month:02d}"
                evidence_id = rolling_row["evidence_id"]
                metric_id = "metric-" + hashlib.sha256(
                    f"{evidence_id}:rolling-12-month:{period}".encode()
                ).hexdigest()[:20]
                cursor = connection.execute(
                    """INSERT OR IGNORE INTO metrics (metric_id, evidence_id, jurisdiction,
                       sector_or_cohort, period_start, period_end, metric_label_raw,
                       metric_label_harmonised, classification_dimension, denominator_definition,
                       raw_value, numeric_value, unit, rate_multiplier, outcome_definition,
                       comparability_status, comparability_note, verification_status)
                       VALUES (?, ?, 'Hong Kong', 'Public works contracts', ?, ?, ?,
                       'Monthly rolling 12-month accident rate', 'Rate',
                       'per 1,000 workers per year', ?, ?, 'accidents per 1,000 workers per year',
                       1000, ?, 'Unassessed', ?, 'Unverified')""",
                    (metric_id, evidence_id, period, period,
                     f"Rolling 12 Month Average - {month_name.title()} {year}", raw_value, numeric_value,
                     f"Rolling 12-month rate reported for {month_name.title()} {year}; this is not an annual calendar-year rate.",
                     "Published monthly observation; denominator and calculation details should be checked against DEVB methodology."),
                )
                if cursor.rowcount:
                    inserted += 1
                detect_metric_conflicts(connection, metric_id)
        audit(connection, "devb_live_rates_extracted", "source_version", source_version_id,
              {"metric_records_added": inserted, "includes_monthly_rolling_averages": True,
               "status": "Unverified; conflicts left unresolved"})
    return inserted


def set_evidence_review(
    connection: sqlite3.Connection,
    evidence_id: str,
    status: str,
    reviewer: str,
    note: str = "",
) -> None:
    """Record a human evidence decision while retaining extracted text."""
    allowed = {"Human-verified", "Rejected", "Unreviewed", "Ambiguous"}
    if status not in allowed:
        raise ValueError(f"Unsupported evidence review status: {status}")
    if status == "Human-verified" and (not reviewer.strip() or not note.strip()):
        raise ValueError("A reviewer and review note are required to mark evidence human-verified.")
    row = connection.execute("SELECT metadata_json FROM evidence WHERE evidence_id = ?", (evidence_id,)).fetchone()
    if row is None:
        raise ValueError("Evidence record not found.")
    metadata = json.loads(row["metadata_json"] or "{}")
    metadata["review_note"] = note
    with connection:
        connection.execute(
            "UPDATE evidence SET review_status=?, reviewer=?, metadata_json=? WHERE evidence_id=?",
            (status, reviewer or None, json.dumps(metadata, ensure_ascii=False), evidence_id),
        )
        table_row = connection.execute("SELECT row_id FROM extracted_table_rows WHERE evidence_id=?", (evidence_id,)).fetchone()
        if table_row:
            connection.execute(
                "UPDATE extracted_table_rows SET review_status=?, reviewer=?, review_note=? WHERE evidence_id=?",
                (status, reviewer or None, note, evidence_id),
            )
            audit(connection, "table_row_reviewed", "extracted_table_row", table_row["row_id"],
                  {"status": status, "reviewer": reviewer, "note": note, "via_evidence": evidence_id})
        audit(connection, "evidence_reviewed", "evidence", evidence_id,
              {"status": status, "reviewer": reviewer, "note": note})


def extract_pdf_tables(pdf_path: Path, source_version_id: str, connection: sqlite3.Connection) -> int:
    """Extract candidate PDF table rows without normalizing or interpreting cells.

    Each cell is retained as raw text (including None for blank cells). Table and
    row indices are zero-based within each page and extraction run is idempotent.
    """
    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("PDF table extraction needs pdfplumber. Install project dependencies with pip install -r requirements.txt.") from exc

    inserted = 0
    with pdfplumber.open(pdf_path) as pdf:
        with connection:
            for page_number, page in enumerate(pdf.pages, start=1):
                for table_index, table in enumerate(page.extract_tables() or []):
                    for row_index, row in enumerate(table):
                        row_id = "row-" + hashlib.sha256(
                            f"{source_version_id}:{page_number}:{table_index}:{row_index}".encode()
                        ).hexdigest()[:20]
                        exists = connection.execute("SELECT 1 FROM extracted_table_rows WHERE row_id=?", (row_id,)).fetchone()
                        if exists:
                            continue
                        raw_cells = [None if cell is None else str(cell) for cell in row]
                        raw_cells_json = json.dumps(raw_cells, ensure_ascii=False)
                        evidence_id = "ev-" + hashlib.sha256(
                            f"{source_version_id}:table:{page_number}:{table_index}:{row_index}".encode()
                        ).hexdigest()[:20]
                        evidence_exists = connection.execute(
                            "SELECT 1 FROM evidence WHERE evidence_id=?", (evidence_id,)
                        ).fetchone()
                        if not evidence_exists:
                            connection.execute(
                                """INSERT INTO evidence (evidence_id, source_version_id, page_or_section,
                                   exact_quote_or_excerpt, locator_type, extraction_method, review_status,
                                   reviewer, confidence, metadata_json, created_at)
                                   VALUES (?, ?, ?, ?, 'PDF page+table+row', 'pdfplumber table parser',
                                   'Unreviewed', NULL, 'medium', ?, ?)""",
                                (evidence_id, source_version_id,
                                 f"PDF page {page_number}, table {table_index + 1}, row {row_index + 1}",
                                 raw_cells_json,
                                 json.dumps({"page_number": page_number, "table_index": table_index,
                                             "row_index": row_index, "raw_cells": raw_cells}, ensure_ascii=False),
                                 now_iso()),
                            )
                        connection.execute(
                            """INSERT INTO extracted_table_rows (row_id, source_version_id, evidence_id,
                               page_number, table_index, row_index, raw_cells_json, review_status, extracted_at)
                               VALUES (?, ?, ?, ?, ?, ?, ?, 'Unreviewed', ?)""",
                            (row_id, source_version_id, evidence_id, page_number, table_index, row_index,
                             raw_cells_json, now_iso()),
                        )
                        inserted += 1
            audit(connection, "pdf_tables_extracted", "source_version", source_version_id,
                  {"new_candidate_rows": inserted})
    return inserted


def _store_candidate_row(
    connection: sqlite3.Connection,
    source_version_id: str,
    locator_key: str,
    page_number: int,
    table_index: int,
    row_index: int,
    locator: str,
    raw_cells: list[str | None],
    extraction_method: str,
) -> bool:
    """Store source-faithful cells and linked evidence for one candidate row."""
    row_id = "row-" + hashlib.sha256(f"{source_version_id}:{locator_key}".encode()).hexdigest()[:20]
    if connection.execute("SELECT 1 FROM extracted_table_rows WHERE row_id=?", (row_id,)).fetchone():
        return False
    raw_cells_json = json.dumps(raw_cells, ensure_ascii=False)
    evidence_id = "ev-" + hashlib.sha256(f"{source_version_id}:row:{locator_key}".encode()).hexdigest()[:20]
    if not connection.execute("SELECT 1 FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone():
        connection.execute(
            """INSERT INTO evidence (evidence_id, source_version_id, page_or_section,
               exact_quote_or_excerpt, locator_type, extraction_method, review_status,
               reviewer, confidence, metadata_json, created_at)
               VALUES (?, ?, ?, ?, 'dataset row', ?, 'Unreviewed', NULL, 'medium', ?, ?)""",
            (evidence_id, source_version_id, locator, raw_cells_json,
             extraction_method, json.dumps({"raw_cells": raw_cells, "locator": locator}, ensure_ascii=False), now_iso()),
        )
    connection.execute(
        """INSERT INTO extracted_table_rows (row_id, source_version_id, evidence_id,
           page_number, table_index, row_index, raw_cells_json, review_status, extracted_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'Unreviewed', ?)""",
        (row_id, source_version_id, evidence_id, page_number, table_index, row_index,
         raw_cells_json, now_iso()),
    )
    return True


def extract_csv_rows(path: Path, source_version_id: str, connection: sqlite3.Connection) -> int:
    """Import CSV rows as provisional raw-cell records; blanks remain empty strings."""
    inserted = 0
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        with connection:
            for row_index, row in enumerate(reader):
                cells = [str(cell) for cell in row]
                inserted += _store_candidate_row(
                    connection, source_version_id, f"csv:0:{row_index}", 0, 0, row_index,
                    f"CSV row {row_index + 1}", cells, "CSV parser",
                )
            audit(connection, "csv_rows_extracted", "source_version", source_version_id,
                  {"new_candidate_rows": inserted})
    return inserted


def extract_xlsx_rows(path: Path, source_version_id: str, connection: sqlite3.Connection) -> int:
    """Import worksheet rows as provisional records, preserving blanks and formulas."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise RuntimeError("XLSX extraction needs openpyxl. Install project dependencies with pip install -r requirements.txt.") from exc

    inserted = 0
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        with connection:
            for sheet_index, sheet in enumerate(workbook.worksheets):
                for row_index, row in enumerate(sheet.iter_rows(values_only=True)):
                    cells = [None if value is None else str(value) for value in row]
                    inserted += _store_candidate_row(
                        connection, source_version_id, f"xlsx:{sheet_index}:{row_index}", 0,
                        sheet_index, row_index, f"XLSX sheet {sheet.title}, row {row_index + 1}",
                        cells, "openpyxl workbook parser",
                    )
            audit(connection, "xlsx_rows_extracted", "source_version", source_version_id,
                  {"new_candidate_rows": inserted, "sheets": workbook.sheetnames})
    finally:
        workbook.close()
    return inserted


def extract_docx_tables(path: Path, source_version_id: str, connection: sqlite3.Connection) -> int:
    """Import Word tables as candidate rows with table/row locators."""
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("DOCX extraction needs python-docx. Install project dependencies with pip install -r requirements.txt.") from exc

    document = Document(path)
    inserted = 0
    with connection:
        for table_index, table in enumerate(document.tables):
            for row_index, row in enumerate(table.rows):
                cells = [cell.text for cell in row.cells]
                inserted += _store_candidate_row(
                    connection, source_version_id, f"docx:{table_index}:{row_index}", 0,
                    table_index, row_index, f"DOCX table {table_index + 1}, row {row_index + 1}",
                    cells, "python-docx table parser",
                )
        audit(connection, "docx_tables_extracted", "source_version", source_version_id,
              {"new_candidate_rows": inserted, "tables": len(document.tables)})
    return inserted


def extract_devb_appendices(path: Path, source_version_id: str, connection: sqlite3.Connection) -> int:
    """Create unverified count/percentage metrics from DEVB Appendix H–O tables.

    The parser identifies appendices by their page headings and finds the 2025
    columns from the extracted header. Denominators come from each table's own
    total row; when the total includes a parenthesized accident count, the first
    number is retained as the coded-record denominator. Raw source cells remain
    attached through the row evidence record.
    """
    from decimal import Decimal, InvalidOperation

    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("DEVB appendix parsing needs pdfplumber.") from exc

    dimensions = {
        "H": "Accident type", "I": "Trade", "J": "Injury nature", "K": "Body part",
        "L": "Agent", "M": "Unsafe action", "N": "Unsafe condition", "O": "Personal factor",
    }

    def numeric_cell(value: str | None) -> float | None:
        if value is None:
            return None
        clean = value.strip().replace(",", "")
        if not clean or clean in {"-", "—", "–"}:
            return None
        match = re.fullmatch(r"[+-]?\d+(?:\.\d+)?", clean)
        if not match:
            return None
        try:
            return float(Decimal(clean))
        except InvalidOperation:
            return None

    inserted = 0
    parsed_rows = 0
    with pdfplumber.open(path) as pdf:
        with connection:
            for page_number, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                appendix_match = re.search(r"\bAppendix\s+([H-O])\b", page_text, re.IGNORECASE)
                if not appendix_match:
                    continue
                appendix = appendix_match.group(1).upper()
                tables = page.extract_tables() or []
                for table_index, table in enumerate(tables):
                    year_column = next(
                        (index for row in table[:2] for index, cell in enumerate(row)
                         if cell and cell.strip() == "2025"),
                        None,
                    )
                    if year_column is None or year_column + 1 >= max((len(row) for row in table), default=0):
                        continue
                    count_column, percent_column = year_column, year_column + 1
                    def is_total_row(row: list[str | None]) -> bool:
                        label_text = " ".join((row[0] or "").casefold().split()) if row else ""
                        return "total" in label_text and "sub-total" not in label_text

                    total_row = next((row for row in table if is_total_row(row)), None)
                    if total_row is None or count_column >= len(total_row):
                        continue
                    denominator_raw = total_row[count_column]
                    denominator_match = re.search(r"([\d,]+)(?:\s*\(\s*([\d,]+)\s*\))?", denominator_raw or "")
                    if not denominator_match:
                        continue
                    denominator = float(denominator_match.group(1).replace(",", ""))
                    accident_count = denominator_match.group(2)
                    if accident_count:
                        denominator_definition = (
                            f"{int(denominator)} coded {dimensions[appendix].lower()} records; "
                            f"{int(accident_count.replace(',', ''))} accidents shown in parentheses in Appendix {appendix} total row"
                        )
                    else:
                        denominator_definition = f"{int(denominator)} total accidents in Appendix {appendix}"

                    for row_index, row in enumerate(table):
                        if row_index < 2 or not row or not row[0] or not row[0].strip():
                            continue
                        label = row[0].strip()
                        normalized_label = " ".join(label.casefold().split())
                        if "sub-total" in normalized_label or is_total_row(row):
                            continue
                        if count_column >= len(row) or percent_column >= len(row):
                            continue
                        count_raw = row[count_column]
                        percent_raw = row[percent_column]
                        if count_raw is None and percent_raw is None:
                            continue
                        evidence = connection.execute(
                            """SELECT evidence_id FROM extracted_table_rows WHERE source_version_id=?
                               AND page_number=? AND table_index=? AND row_index=?""",
                            (source_version_id, page_number, table_index, row_index),
                        ).fetchone()
                        if evidence is None:
                            continue
                        parsed_rows += 1
                        count_value = numeric_cell(count_raw)
                        percent_value = numeric_cell(percent_raw.rstrip("%") if percent_raw else None)
                        evidence_id = evidence["evidence_id"]
                        common = ("Hong Kong", "Public works contracts", "2025", "2025", label,
                                  dimensions[appendix])
                        for suffix, raw_value, numeric_value, unit, numerator, den_value, den_definition in (
                            ("count", count_raw, count_value, "category records", None, None,
                             f"Not a ratio; source count in Appendix {appendix}"),
                            ("percent", percent_raw, percent_value, "percent", count_value, denominator,
                             denominator_definition),
                        ):
                            if raw_value is None:
                                continue
                            metric_id = "metric-" + hashlib.sha256(f"{evidence_id}:{suffix}:2025".encode()).hexdigest()[:20]
                            cursor = connection.execute(
                                """INSERT OR IGNORE INTO metrics (metric_id, evidence_id, jurisdiction,
                                   sector_or_cohort, period_start, period_end, metric_label_raw,
                                   classification_dimension, numerator, denominator, denominator_definition,
                                   raw_value, numeric_value, unit, verification_status)
                                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Unverified')""",
                                (metric_id, evidence_id, common[0], common[1], common[2], common[3],
                                 common[4], common[5], numerator, den_value, den_definition,
                                 raw_value, numeric_value, unit),
                            )
                            if cursor.rowcount:
                                inserted += 1
                    
            audit(connection, "devb_appendix_metrics_extracted", "source_version", source_version_id,
                  {"appendix_range": "H-O", "candidate_rows": parsed_rows,
                   "metric_records_added": inserted, "period": 2025,
                   "status": "Unverified; human review required"})
    return inserted


def extract_devb_appendix_a(path: Path, source_version_id: str, connection: sqlite3.Connection) -> int:
    """Extract Appendix A annual rates and source counts as unverified metrics."""
    from decimal import Decimal, InvalidOperation

    try:
        import pdfplumber
    except ImportError as exc:
        raise RuntimeError("DEVB Appendix A extraction needs pdfplumber.") from exc

    def number(value: str | None) -> float | None:
        if value is None:
            return None
        text = value.strip().replace(",", "")
        if not text or text in {"-", "—", "–"}:
            return None
        try:
            return float(Decimal(text))
        except InvalidOperation:
            return None

    inserted = 0
    with pdfplumber.open(path) as pdf:
        with connection:
            for page_number, page in enumerate(pdf.pages, start=1):
                page_text = page.extract_text() or ""
                if not re.search(r"\bAppendix\s+A\b", page_text, re.IGNORECASE):
                    continue
                for table_index, table in enumerate(page.extract_tables() or []):
                    for row_index, row in enumerate(table):
                        if not row or not row[0] or not re.fullmatch(r"20\d{2}", row[0].strip()):
                            continue
                        year = row[0].strip()
                        evidence = connection.execute(
                            """SELECT evidence_id FROM extracted_table_rows WHERE source_version_id=?
                               AND page_number=? AND table_index=? AND row_index=?""",
                            (source_version_id, page_number, table_index, row_index),
                        ).fetchone()
                        if evidence is None or len(row) < 10:
                            continue
                        evidence_id = evidence["evidence_id"]
                        fatal_count = number(row[1])
                        nonfatal_count = number(row[2])
                        man_hours = number(row[3])
                        total_count = fatal_count + nonfatal_count if fatal_count is not None and nonfatal_count is not None else None

                        records: list[dict[str, Any]] = [
                            {"label": "No. of Fatalities", "raw": row[1], "value": fatal_count,
                             "dimension": "Severity", "unit": "fatalities", "definition": "Not a ratio; fatality count reported in Appendix A"},
                            {"label": "No. of Non-fatal Reportable Accidents", "raw": row[2], "value": nonfatal_count,
                             "dimension": "Severity", "unit": "accidents", "definition": "Not a ratio; non-fatal reportable accident count reported in Appendix A"},
                            {"label": "No. of Man-hours Worked", "raw": row[3], "value": man_hours,
                             "dimension": "Exposure", "unit": "man-hours", "definition": "Exposure denominator as defined in Appendix A footnote 3"},
                            {"label": "Fatal Accidents rate (a)", "raw": row[4], "value": number(row[4]),
                             "dimension": "Rate", "unit": "accidents per 100,000 man-hours", "numerator": fatal_count,
                             "denominator": man_hours, "definition": "Man-hours worked; Appendix A footnote 4", "multiplier": 100000,
                             "formula": "fatal accidents / man-hours worked * 100000"},
                            {"label": "Fatal Accidents rate (b)", "raw": row[5], "value": number(row[5]),
                             "dimension": "Rate", "unit": "accidents per 1,000 workers per year", "numerator": fatal_count,
                             "definition": "Workers per year; conversion defined in Appendix A footnote 5", "multiplier": 1000},
                            {"label": "Fatal Accidents rate (c)", "raw": row[6], "value": number(row[6]),
                             "dimension": "Rate", "unit": "accidents per 1,000 workers per year", "cohort": "Construction industry",
                             "definition": "Construction-industry rate based on Labour Department statistics; Appendix A footnote 6", "multiplier": 1000},
                            {"label": "Reportable Accidents rate (a)", "raw": row[7], "value": number(row[7]),
                             "dimension": "Rate", "unit": "accidents per 100,000 man-hours", "numerator": total_count,
                             "denominator": man_hours, "definition": "Man-hours worked; numerator derived as fatalities plus non-fatal reportable accidents",
                             "multiplier": 100000, "formula": "(fatal accidents + non-fatal reportable accidents) / man-hours worked * 100000"},
                            {"label": "Reportable Accidents rate (b)", "raw": row[8], "value": number(row[8]),
                             "dimension": "Rate", "unit": "accidents per 1,000 workers per year", "numerator": total_count,
                             "definition": "per 1,000 workers per year",
                             "multiplier": 1000, "formula": "Published rate; numerator is fatalities plus non-fatal reportable accidents",
                             "harmonised": "Reportable accident rate per 1,000 workers per year"},
                            {"label": "Reportable Accidents rate (c)", "raw": row[9], "value": number(row[9]),
                             "dimension": "Rate", "unit": "accidents per 1,000 workers per year", "cohort": "Construction industry",
                             "definition": "Construction-industry rate based on Labour Department statistics; Appendix A footnote 6", "multiplier": 1000},
                        ]
                        if total_count is not None:
                            records.append({
                                "label": "Total reportable accidents (derived)",
                                "raw": f"{row[1]} + {row[2]} = {int(total_count)}", "value": total_count,
                                "dimension": "Severity", "unit": "accidents",
                                "definition": "Derived as fatalities plus non-fatal reportable accidents from the same Appendix A row",
                                "formula": "fatalities + non-fatal reportable accidents",
                            })
                        for record in records:
                            if record.get("raw") is None:
                                continue
                            cohort = record.get("cohort", "Public works contracts")
                            metric_id = "metric-" + hashlib.sha256(
                                f"{evidence_id}:appendix-a:{year}:{record['label']}:{cohort}".encode()
                            ).hexdigest()[:20]
                            if record.get("harmonised"):
                                # Backfill deterministic metadata on records
                                # extracted by an earlier parser revision.
                                connection.execute(
                                    """UPDATE metrics SET metric_label_harmonised=?, denominator_definition=?
                                       WHERE metric_id=? AND (metric_label_harmonised IS NULL OR metric_label_harmonised='')""",
                                    (record["harmonised"], record["definition"], metric_id),
                                )
                            cursor = connection.execute(
                                """INSERT OR IGNORE INTO metrics (metric_id, evidence_id, jurisdiction,
                                   sector_or_cohort, period_start, period_end, metric_label_raw,
                                   metric_label_harmonised, classification_dimension, numerator, denominator, denominator_definition,
                                   raw_value, numeric_value, unit, rate_multiplier, formula, verification_status)
                                   VALUES (?, ?, 'Hong Kong', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Unverified')""",
                                (metric_id, evidence_id, cohort, year, year, record["label"],
                                 record.get("harmonised"), record["dimension"], record.get("numerator"),
                                 record.get("denominator"), record["definition"],
                                 record["raw"], record.get("value"), record["unit"], record.get("multiplier"),
                                 record.get("formula")),
                            )
                            if cursor.rowcount:
                                inserted += 1
            audit(connection, "devb_appendix_a_metrics_extracted", "source_version", source_version_id,
                  {"metric_records_added": inserted, "years": "2016-2025", "status": "Unverified"})
    return inserted


def extract_ombudsman_di464_metrics(source_version_id: str, connection: sqlite3.Connection) -> int:
    """Create unverified metrics from the fatal-accident tables in DI/464.

    The parser uses the retained raw table rows on report PDF pages 30–32.
    Counts and within-construction fatal-accident shares remain distinct from
    DEVB reportable-accident rates and are explicitly context-only.
    """
    import json
    from decimal import Decimal, InvalidOperation

    def number(value: str | None) -> float | None:
        if not value:
            return None
        match = re.search(r"\d[\d,]*(?:\.\d+)?", value.replace("\n", " "))
        if not match:
            return None
        try:
            return float(Decimal(match.group(0).replace(",", "")))
        except InvalidOperation:
            return None

    rows = connection.execute(
        """SELECT page_number, table_index, row_index, evidence_id, raw_cells_json
           FROM extracted_table_rows WHERE source_version_id=? AND page_number BETWEEN 30 AND 32
           ORDER BY page_number, table_index, row_index""",
        (source_version_id,),
    ).fetchall()
    inserted = 0

    def add_metric(evidence_id: str, period: str, label: str, dimension: str,
                   raw: str, value: float | None, unit: str, definition: str,
                   outcome: str, numerator: float | None = None,
                   denominator: float | None = None) -> None:
        nonlocal inserted
        metric_id = "metric-" + hashlib.sha256(
            f"{evidence_id}:di464:{period}:{label}:{unit}".encode("utf-8")
        ).hexdigest()[:20]
        cursor = connection.execute(
            """INSERT OR IGNORE INTO metrics (metric_id, evidence_id, jurisdiction,
               sector_or_cohort, period_start, period_end, metric_label_raw,
               metric_label_harmonised, classification_dimension, numerator, denominator,
               denominator_definition, raw_value, numeric_value, unit, outcome_definition,
               comparability_status, comparability_note, verification_status)
               VALUES (?, ?, 'Hong Kong', 'Construction industry', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
               'Context only', ?, 'Unverified')""",
            (metric_id, evidence_id, period.split("-")[0], period.split("-")[-1], label,
             label, dimension, numerator, denominator, definition, raw, value, unit, outcome,
             "DI/464 fatal industrial-accident scope differs from the DEVB public-works reportable-accident series."),
        )
        inserted += cursor.rowcount

    with connection:
        for row in rows:
            cells = json.loads(row["raw_cells_json"])
            page_number = row["page_number"]
            if page_number == 30 and row["table_index"] == 0 and cells and cells[0] in {"2018", "2019", "2020", "2021", "2022", "2023"}:
                year = cells[0]
                all_industries = number(cells[1] if len(cells) > 1 else None)
                construction = number(cells[4] if len(cells) > 4 else None)
                for label, raw, value, cohort in (
                    ("Fatal industrial accidents, all industries", cells[1], all_industries, "All industries including construction"),
                    ("Fatal industrial accidents, construction industry", cells[4], construction, "Construction industry"),
                ):
                    if value is not None:
                        add_metric(row["evidence_id"], year, label, "Fatal accident count", raw,
                                   value, "fatal industrial accidents", f"Annual fatal industrial-accident count; cohort: {cohort}.",
                                   f"Fatal industrial accidents in {cohort}")

            elif page_number == 31 and row["table_index"] == 0 and cells and cells[0] in {"2018", "2019", "2020", "2021", "2022", "2023"}:
                year = cells[0]
                total = number(cells[7] if len(cells) > 7 else None)
                categories = (
                    ("New works, public-works-related", 1),
                    ("New works, not public-works-related", 3),
                    ("Renovation and repair works", 6),
                )
                for label, index in categories:
                    raw = cells[index] if len(cells) > index else None
                    count = number(raw)
                    if raw is None or count is None:
                        continue
                    definition = f"Fatal industrial accidents in {label.lower()} for this year."
                    add_metric(row["evidence_id"], year, f"Fatal accidents: {label}", "Work-scope fatality count",
                               raw, count, "fatal industrial accidents", definition,
                               f"Construction fatal industrial accidents classified by {label.lower()}")
                    percent_match = re.search(r"\(\s*([\d.]+)\s*%\s*\)", raw)
                    if percent_match:
                        percent = number(percent_match.group(1))
                        add_metric(row["evidence_id"], year, f"Fatal accident share: {label}", "Work-scope share",
                                   f"{percent_match.group(1)}%", percent, "percent",
                                   f"{count:g} / {total:g} construction fatal industrial accidents in {year}.",
                                   f"Share of annual construction fatal industrial accidents classified by {label.lower()}",
                                   count, total)

            elif page_number == 32 and row["table_index"] == 0 and cells and cells[0] and cells[0].strip().casefold() != "total":
                years = connection.execute(
                    """SELECT raw_cells_json FROM extracted_table_rows
                       WHERE source_version_id=? AND page_number=32 AND table_index=0 AND row_index=0""",
                    (source_version_id,),
                ).fetchone()
                if not years:
                    continue
                header = json.loads(years["raw_cells_json"])
                label = " ".join(cells[0].split())
                if label.casefold() == "year" or not re.match(r"^20\d{2}$", str(header[1] if len(header)>1 else "")):
                    continue
                for column, year in enumerate(header[1:7], start=1):
                    value = number(cells[column] if len(cells) > column else None)
                    if value is None:
                        continue
                    add_metric(row["evidence_id"], str(year), f"Fatal accidents by type: {label}", "Fatal accident type",
                               str(cells[column]), value, "fatal industrial accidents",
                               f"Annual count of construction fatal industrial accidents classified as {label}.",
                               f"Construction fatal industrial accidents by type: {label}")

        audit(connection, "ombudsman_di464_metrics_extracted", "source_version", source_version_id,
              {"metric_records_added": inserted, "tables": "DI/464 Tables 1-3", "status": "Unverified; context-only"})
    return inserted


def set_table_row_review(
    connection: sqlite3.Connection,
    row_id: str,
    status: str,
    reviewer: str,
    note: str = "",
) -> None:
    """Set human review state while preserving the original raw cell array."""
    allowed = {"Human-verified", "Rejected", "Unreviewed", "Ambiguous"}
    if status not in allowed:
        raise ValueError(f"Unsupported table row review status: {status}")
    if status == "Human-verified" and (not reviewer.strip() or not note.strip()):
        raise ValueError("A reviewer and review note are required to mark a table row human-verified.")
    exists = connection.execute("SELECT evidence_id FROM extracted_table_rows WHERE row_id=?", (row_id,)).fetchone()
    if not exists:
        raise ValueError("Extracted table row not found.")
    evidence = connection.execute("SELECT metadata_json FROM evidence WHERE evidence_id=?", (exists["evidence_id"],)).fetchone()
    metadata = json.loads(evidence["metadata_json"] or "{}") if evidence else {}
    metadata["review_note"] = note
    with connection:
        connection.execute(
            "UPDATE extracted_table_rows SET review_status=?, reviewer=?, review_note=? WHERE row_id=?",
            (status, reviewer or None, note, row_id),
        )
        connection.execute(
            "UPDATE evidence SET review_status=?, reviewer=?, metadata_json=? WHERE evidence_id=?",
            (status, reviewer or None, json.dumps(metadata, ensure_ascii=False), exists["evidence_id"]),
        )
        audit(connection, "table_row_reviewed", "extracted_table_row", row_id,
              {"status": status, "reviewer": reviewer, "note": note})
        audit(connection, "evidence_reviewed", "evidence", exists["evidence_id"],
              {"status": status, "reviewer": reviewer, "note": note, "via_table_row": row_id})
