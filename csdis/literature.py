"""Polite Crossref/OpenAlex discovery with query and deduplication records."""

from __future__ import annotations

import json
import hashlib
import mimetypes
import re
import sqlite3
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import httpx

from csdis.database import audit, now_iso


def normalize_doi(value: str | None) -> str | None:
    """Return a normalized DOI or None when metadata contains no DOI."""
    if not value:
        return None
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", value.strip(), flags=re.IGNORECASE)
    doi = doi.strip().lower()
    return doi or None


def _year(value: Any) -> int | None:
    try:
        year = int(value)
        return year if 1000 <= year <= 9999 else None
    except (TypeError, ValueError):
        return None


def _duplicate_candidate(connection: sqlite3.Connection, doi: str | None, title: str, year: int | None) -> tuple[str, str] | None:
    if doi:
        match = connection.execute(
            "SELECT record_id FROM literature_records WHERE lower(doi)=? ORDER BY imported_at LIMIT 1",
            (doi,),
        ).fetchone()
        if match:
            return "Potential DOI duplicate", match["record_id"]
    normalized_title = " ".join(title.casefold().split())
    for row in connection.execute("SELECT record_id, title, year FROM literature_records WHERE title!=''"):
        if year is not None and row["year"] is not None and abs(year - row["year"]) > 1:
            continue
        candidate = " ".join(row["title"].casefold().split())
        if normalized_title and SequenceMatcher(None, normalized_title, candidate).ratio() >= 0.96:
            return "Potential near-title duplicate", row["record_id"]
    return None


def _save_search(
    connection: sqlite3.Connection,
    database_name: str,
    query_text: str,
    page_size: int,
    filters: dict[str, Any],
    records: list[dict[str, Any]],
    error: str | None = None,
) -> dict[str, Any]:
    query_id = "lit-search-" + uuid.uuid4().hex[:16]
    timestamp = now_iso()
    status = "Failed" if error else "Completed"
    with connection:
        connection.execute(
            """INSERT INTO literature_searches (query_id, database_name, query_text, searched_at,
               result_count, page_size, filters_json, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (query_id, database_name, query_text, timestamp, len(records), page_size,
             json.dumps(filters, ensure_ascii=False), status, error),
        )
        added = 0
        duplicates = 0
        for record in records:
            title = (record.get("title") or "").strip()
            if not title:
                continue
            doi = normalize_doi(record.get("doi"))
            year = _year(record.get("year"))
            authors = record.get("authors") or []
            if isinstance(authors, str):
                authors_text = authors
            else:
                authors_text = "; ".join(str(author) for author in authors if author)
            duplicate = _duplicate_candidate(connection, doi, title, year)
            duplicate_status, duplicate_of = duplicate if duplicate else ("No duplicate detected", None)
            if duplicate:
                duplicates += 1
            record_id = "lit-" + uuid.uuid4().hex[:16]
            connection.execute(
                """INSERT INTO literature_records (record_id, doi, title, authors, year, venue,
                   database_name, query_id, external_id, record_url, duplicate_status, duplicate_of,
                   imported_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (record_id, doi, title, authors_text, year, record.get("venue"), database_name,
                 query_id, record.get("external_id"), record.get("url"), duplicate_status,
                 duplicate_of, timestamp),
            )
            added += 1
        audit(connection, "literature_search_completed" if not error else "literature_search_failed",
              "literature_search", query_id,
              {"database": database_name, "query": query_text, "result_count": len(records),
               "records_added": added, "possible_duplicates": duplicates, "error": error})
    return {"query_id": query_id, "database": database_name, "count": len(records),
            "added": added, "duplicates": duplicates, "error": error,
            "page": filters.get("page", 1), "total_results": filters.get("total_results")}


def search_crossref(connection: sqlite3.Connection, query_text: str, page_size: int = 25,
                    page: int = 1) -> dict[str, Any]:
    """Search one offset page of Crossref bibliographic metadata and log it."""
    page_size = max(1, min(int(page_size), 100))
    page = max(1, min(int(page), max(1, 10000 // page_size)))
    offset = (page - 1) * page_size
    params = {"query.bibliographic": query_text, "rows": page_size, "offset": offset}
    filters = {**params, "page": page}
    try:
        response = httpx.get("https://api.crossref.org/works", params=params,
                             timeout=httpx.Timeout(20.0, connect=10.0),
                             headers={"User-Agent": "CSDIS literature discovery/0.1"})
        response.raise_for_status()
        message = response.json().get("message", {})
        filters["total_results"] = int(message.get("total-results") or 0)
        items = message.get("items", [])
        results = []
        for item in items:
            title_values = item.get("title") or []
            authors = [" ".join(part for part in [author.get("given"), author.get("family")] if part)
                       for author in item.get("author", [])]
            date_parts = ((item.get("published-print") or item.get("published-online") or item.get("issued") or {})
                          .get("date-parts") or [[None]])
            results.append({
                "doi": item.get("DOI"), "title": title_values[0] if title_values else "",
                "authors": authors, "year": (date_parts[0] or [None])[0],
                "venue": (item.get("container-title") or [None])[0],
                "external_id": item.get("DOI"), "url": item.get("URL"),
            })
        return _save_search(connection, "Crossref", query_text, page_size, filters, results)
    except Exception as exc:
        return _save_search(connection, "Crossref", query_text, page_size, filters, [], str(exc)[:1000])


def search_openalex(connection: sqlite3.Connection, query_text: str, page_size: int = 25,
                    page: int = 1) -> dict[str, Any]:
    """Search one page of OpenAlex works metadata and log the query."""
    page_size = max(1, min(int(page_size), 100))
    page = max(1, min(int(page), 10000))
    params = {"search": query_text, "per_page": page_size, "page": page}
    try:
        response = httpx.get("https://api.openalex.org/works", params=params,
                             timeout=httpx.Timeout(20.0, connect=10.0),
                             headers={"User-Agent": "CSDIS literature discovery/0.1"})
        response.raise_for_status()
        payload = response.json()
        params["total_results"] = int((payload.get("meta") or {}).get("count") or 0)
        results = []
        for item in payload.get("results", []):
            authors = [((authorship.get("author") or {}).get("display_name") or "")
                       for authorship in item.get("authorships", [])]
            source = ((item.get("primary_location") or {}).get("source") or {}).get("display_name")
            results.append({
                "doi": item.get("doi"), "title": item.get("title") or "",
                "authors": authors, "year": item.get("publication_year"),
                "venue": source, "external_id": item.get("id"), "url": item.get("doi") or item.get("id"),
            })
        return _save_search(connection, "OpenAlex", query_text, page_size, params, results)
    except Exception as exc:
        return _save_search(connection, "OpenAlex", query_text, page_size, params, [], str(exc)[:1000])


def _bibtex_escape(value: str) -> str:
    """Escape a field value for a BibTeX braced literal."""
    replacements = {
        "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}",
        "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
        "_": r"\_", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in value)


def export_bibtex(records: list[dict[str, Any]]) -> str:
    """Serialize discovered records as BibTeX misc entries with screening notes."""
    entries = []
    for record in records:
        title = str(record.get("title") or "").strip()
        if not title:
            continue
        authors = [part.strip() for part in str(record.get("authors") or "").split(";") if part.strip()]
        lead = re.sub(r"[^A-Za-z0-9]+", "", (authors[0].split()[-1] if authors else "record")) or "record"
        year = str(record.get("year") or "nd")
        key = f"{lead}{year}_{str(record.get('record_id') or 'item')[-6:]}"
        fields = [
            ("title", title), ("author", " and ".join(authors)),
            ("year", str(record.get("year") or "")), ("journal", str(record.get("venue") or "")),
            ("doi", str(record.get("doi") or "")), ("url", str(record.get("record_url") or "")),
            ("note", f"Screening: {record.get('screening_status') or 'Unscreened'}; "
                     f"full text: {record.get('full_text_status') or 'Metadata only'}; "
                     f"duplicate review: {record.get('duplicate_status') or 'No duplicate detected'}"),
        ]
        rendered = [f"  {name} = {{{_bibtex_escape(value)}}}," for name, value in fields if value]
        entries.append(f"@misc{{{key},\n" + "\n".join(rendered) + "\n}")
    return "\n\n".join(entries) + ("\n" if entries else "")


def export_ris(records: list[dict[str, Any]]) -> str:
    """Serialize metadata records as generic RIS entries with screening notes."""
    entries = []
    for record in records:
        title = str(record.get("title") or "").strip()
        if not title:
            continue
        lines = ["TY  - GEN", f"TI  - {title}"]
        lines.extend(f"AU  - {author.strip()}" for author in str(record.get("authors") or "").split(";") if author.strip())
        if record.get("year"):
            lines.append(f"PY  - {record['year']}")
        if record.get("venue"):
            lines.append(f"JO  - {record['venue']}")
        if record.get("doi"):
            lines.append(f"DO  - {record['doi']}")
        if record.get("record_url"):
            lines.append(f"UR  - {record['record_url']}")
        if record.get("record_id"):
            lines.append(f"ID  - {record['record_id']}")
        lines.append("N1  - Screening: " + str(record.get("screening_status") or "Unscreened")
                     + "; full text: " + str(record.get("full_text_status") or "Metadata only")
                     + "; duplicate review: " + str(record.get("duplicate_status") or "No duplicate detected"))
        lines.append("ER  - ")
        entries.append("\n".join(lines))
    return "\n\n".join(entries) + ("\n" if entries else "")


def store_full_text(
    connection: sqlite3.Connection,
    storage_root: Path,
    record_id: str,
    original_filename: str,
    content: bytes,
    content_type: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Store an immutable, content-addressed full-text attachment for a record."""
    if not content:
        raise ValueError("The full-text file is empty.")
    if len(content) > 100 * 1024 * 1024:
        raise ValueError("The full-text file exceeds the 100 MiB limit.")
    if not connection.execute("SELECT 1 FROM literature_records WHERE record_id=?", (record_id,)).fetchone():
        raise ValueError("Literature record not found.")

    safe_record_id = re.sub(r"[^A-Za-z0-9_-]", "_", record_id)
    original_name = Path(original_filename).name or "full-text"
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", original_name)[:120] or "full-text"
    digest = hashlib.sha256(content).hexdigest()
    existing = connection.execute(
        "SELECT * FROM literature_full_texts WHERE record_id=? AND sha256=?",
        (record_id, digest),
    ).fetchone()
    if existing:
        return dict(existing), False

    relative_path = Path(safe_record_id) / f"{digest[:16]}_{safe_name}"
    destination = storage_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if hashlib.sha256(destination.read_bytes()).hexdigest() != digest:
            raise OSError("The content-addressed full-text path already contains different bytes.")
    else:
        with destination.open("xb") as handle:
            handle.write(content)

    file_id = "lit-file-" + uuid.uuid4().hex[:16]
    detected_type = (content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream").split(";")[0]
    timestamp = now_iso()
    with connection:
        connection.execute(
            """INSERT INTO literature_full_texts (file_id, record_id, storage_path,
               original_filename, sha256, file_size, content_type, source_kind, added_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'User upload', ?)""",
            (file_id, record_id, relative_path.as_posix(), original_name, digest,
             len(content), detected_type, timestamp),
        )
        connection.execute("UPDATE literature_records SET full_text_status='User upload' WHERE record_id=?", (record_id,))
        audit(connection, "literature_full_text_attached", "literature_record", record_id,
              {"file_id": file_id, "filename": original_name, "sha256": digest,
               "size": len(content), "content_type": detected_type})
    return dict(connection.execute("SELECT * FROM literature_full_texts WHERE file_id=?", (file_id,)).fetchone()), True


def review_literature_record(
    connection: sqlite3.Connection,
    record_id: str,
    screening_status: str,
    full_text_status: str,
    reviewer: str,
    note: str = "",
    exclusion_reason: str = "",
    duplicate_status: str = "No duplicate detected",
) -> None:
    """Save a human-led screening decision and an audit entry."""
    screening_values = {"Unscreened", "Include", "Exclude", "Maybe", "Full-text pending"}
    full_text_values = {"Metadata only", "OA full text", "User upload", "Unavailable"}
    duplicate_values = {"No duplicate detected", "Potential DOI duplicate", "Potential near-title duplicate", "Confirmed duplicate", "Distinct record"}
    if screening_status not in screening_values or full_text_status not in full_text_values or duplicate_status not in duplicate_values:
        raise ValueError("Unsupported literature screening or full-text status.")
    if screening_status == "Exclude" and not exclusion_reason.strip():
        raise ValueError("Provide an exclusion reason when excluding a record.")
    if (screening_status != "Unscreened" or full_text_status != "Metadata only" or duplicate_status != "No duplicate detected") and (
        not reviewer.strip() or not note.strip()
    ):
        raise ValueError("A reviewer and screening note are required for a screening or full-text decision.")
    if full_text_status == "User upload" and not connection.execute(
        "SELECT 1 FROM literature_full_texts WHERE record_id=? LIMIT 1", (record_id,)
    ).fetchone():
        raise ValueError("Attach a full-text file before setting this status to User upload.")
    with connection:
        cursor = connection.execute(
            """UPDATE literature_records SET screening_status=?, full_text_status=?, reviewer=?,
               review_note=?, exclusion_reason=?, duplicate_status=?,
               duplicate_of=CASE WHEN ?='Distinct record' THEN NULL ELSE duplicate_of END
               WHERE record_id=?""",
            (screening_status, full_text_status, reviewer.strip() or None, note.strip() or None,
             exclusion_reason.strip() or None, duplicate_status, duplicate_status, record_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Literature record not found.")
        audit(connection, "literature_screening_updated", "literature_record", record_id,
              {"screening_status": screening_status, "full_text_status": full_text_status,
               "duplicate_status": duplicate_status,
               "reviewer": reviewer.strip(), "note": note.strip(), "exclusion_reason": exclusion_reason.strip()})
