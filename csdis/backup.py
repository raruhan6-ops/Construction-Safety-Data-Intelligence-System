"""Portable local-data backup generation."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from csdis.database import audit


def create_backup_archive(
    connection: sqlite3.Connection,
    raw_root: Path,
    literature_root: Path | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Return a zip containing the database snapshot and all local source files."""
    audit(connection, "backup_created", "workspace", "local",
          {"includes": ["database", "raw_sources", "literature_full_texts"]})
    connection.commit()

    memory_db = sqlite3.connect(":memory:")
    try:
        connection.backup(memory_db)
        database_bytes = memory_db.serialize()
    finally:
        memory_db.close()

    archive_buffer = io.BytesIO()
    manifest: dict[str, Any] = {
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "database_path": "data/local/csdis.sqlite3",
        "files": [],
    }
    with zipfile.ZipFile(archive_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("data/local/csdis.sqlite3", database_bytes)
        manifest["files"].append({
            "path": "data/local/csdis.sqlite3",
            "size": len(database_bytes),
            "sha256": hashlib.sha256(database_bytes).hexdigest(),
        })
        file_roots = [(raw_root, Path("data/raw"))]
        if literature_root is not None:
            file_roots.append((literature_root, Path("data/literature/full_text")))
        for source_root, archive_prefix in file_roots:
            if not source_root.exists():
                continue
            for path in sorted(candidate for candidate in source_root.rglob("*") if candidate.is_file()):
                relative_path = (archive_prefix / path.relative_to(source_root)).as_posix()
                content = path.read_bytes()
                archive.writestr(relative_path, content)
                manifest["files"].append({
                    "path": relative_path,
                    "size": len(content),
                    "sha256": hashlib.sha256(content).hexdigest(),
                })
        archive.writestr("backup_manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return archive_buffer.getvalue(), manifest
