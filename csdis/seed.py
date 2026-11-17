"""Validated, idempotent importer for the supplied source registry CSV."""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from pydantic import ValidationError

from csdis.database import audit, now_iso
from csdis.schemas import SourceSeed


def import_seed_registry(csv_path: Path, connection: sqlite3.Connection) -> tuple[int, int]:
    """Insert missing seed sources and persist row-level validation errors."""
    inserted = 0
    errors = 0
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required_headers = {
            "source_id", "publisher", "title", "source_type", "url", "format",
            "authority_tier", "frequency", "data_period", "seeded_on", "expected_data",
            "verification_notes",
        }
        headers = set(reader.fieldnames or [])
        missing = required_headers - headers
        if missing:
            raise ValueError("Seed CSV is missing required columns: " + ", ".join(sorted(missing)))

        for row_number, raw in enumerate(reader, start=2):
            try:
                record = SourceSeed.model_validate(raw)
                exists = connection.execute(
                    "SELECT 1 FROM sources WHERE source_id = ?", (record.source_id,)
                ).fetchone()
                if exists:
                    continue
                timestamp = now_iso()
                connection.execute(
                    """INSERT INTO sources (
                      source_id, publisher, title, source_type, canonical_url, format,
                      authority_tier, frequency, data_period, expected_data,
                      verification_notes, created_at, updated_at, origin
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'seed')""",
                    (record.source_id, record.publisher, record.title, record.source_type,
                     record.normalized_url(), record.format, record.authority_tier,
                     record.frequency, record.data_period, record.expected_data,
                     record.verification_notes, timestamp, timestamp),
                )
                audit(connection, "seed_imported", "source", record.source_id, {"row": row_number})
                inserted += 1
            except (ValidationError, ValueError) as exc:
                source_id = (raw.get("source_id") or "").strip() or None
                connection.execute(
                    """INSERT INTO seed_import_errors
                       (imported_at, row_number, source_id, error, raw_row_json)
                       VALUES (?, ?, ?, ?, ?)""",
                    (now_iso(), row_number, source_id, str(exc), json.dumps(raw, ensure_ascii=False)),
                )
                errors += 1
    connection.commit()
    return inserted, errors
