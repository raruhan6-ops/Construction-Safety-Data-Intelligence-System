"""Source registry and immutable local file version handling."""

from __future__ import annotations

import hashlib
import ipaddress
import mimetypes
import re
import sqlite3
import socket
import uuid
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx

from csdis.database import audit, now_iso
from csdis.schemas import SourceRecord


def _validate_public_url(url: str) -> None:
    """Reject local/private targets before making an outbound source request."""
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only absolute HTTP or HTTPS source URLs are supported.")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing embedded credentials are not supported.")
    hostname = parsed.hostname.rstrip(".").lower()
    if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
        raise ValueError("Local and internal network addresses are not valid public source URLs.")
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            addresses = [ipaddress.ip_address(result[4][0]) for result in socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)]
        except OSError as exc:
            raise ValueError(f"Could not resolve public source host {hostname}: {exc}") from exc
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("Source URLs must resolve only to globally routable public addresses.")


def add_source(connection: sqlite3.Connection, record: SourceRecord, origin: str = "manual") -> bool:
    """Add a new source. Existing IDs are left unchanged and return False."""
    existing = connection.execute("SELECT 1 FROM sources WHERE source_id = ?", (record.source_id,)).fetchone()
    if existing:
        return False
    timestamp = now_iso()
    connection.execute(
        """INSERT INTO sources (source_id, publisher, title, source_type, canonical_url,
           format, authority_tier, frequency, data_period, expected_data, verification_notes,
           created_at, updated_at, origin) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (record.source_id, record.publisher, record.title, record.source_type,
         record.canonical_url, record.format, record.authority_tier, record.frequency,
         record.data_period, record.expected_data, record.verification_notes,
         timestamp, timestamp, origin),
    )
    audit(connection, "source_created", "source", record.source_id, {"origin": origin})
    connection.commit()
    return True


def _safe_name(filename: str) -> str:
    name = Path(filename).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:160] or "uploaded_file"


def store_source_version(
    connection: sqlite3.Connection,
    raw_root: Path,
    source_id: str,
    filename: str,
    content: bytes,
    content_type: str | None = None,
    retrieval_method: str = "local_upload",
    http_status: int | None = None,
) -> tuple[str, bool, str]:
    """Store bytes under a content hash; repeated uploads reuse the version."""
    if not connection.execute("SELECT 1 FROM sources WHERE source_id = ?", (source_id,)).fetchone():
        raise ValueError("Choose a registered source before uploading a file.")
    digest = hashlib.sha256(content).hexdigest()
    existing = connection.execute(
        "SELECT source_version_id, storage_path FROM source_versions WHERE source_id = ? AND sha256 = ?",
        (source_id, digest),
    ).fetchone()
    if existing:
        return existing["source_version_id"], False, existing["storage_path"]

    version_id = f"{source_id}-v-{digest}"
    safe_filename = _safe_name(filename)
    relative_path = Path(source_id) / version_id / safe_filename
    destination = raw_root / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    detected_type = content_type or mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
    timestamp = now_iso()
    connection.execute(
        """INSERT INTO source_versions (source_version_id, source_id, version_label,
           original_filename, storage_path, sha256, file_size, content_type, retrieved_at,
           retrieval_method, http_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (version_id, source_id, digest[:12], filename, str(relative_path), digest,
         len(content), detected_type, timestamp, retrieval_method, http_status),
    )
    audit(connection, "source_version_added", "source_version", version_id,
          {"source_id": source_id, "sha256": digest, "file_size": len(content), "method": retrieval_method})
    connection.commit()
    return version_id, True, str(relative_path)


def download_source_version(
    connection: sqlite3.Connection,
    raw_root: Path,
    source_id: str,
    max_bytes: int = 100 * 1024 * 1024,
    timeout_seconds: float = 30.0,
) -> tuple[str, bool, str, int]:
    """Fetch a public HTTP(S) source with bounded size and store it immutably.

    Access restrictions are respected: this makes a standard GET request only,
    without login, paywall, robots or other access-control workarounds.
    """
    source = connection.execute(
        "SELECT canonical_url, title FROM sources WHERE source_id=?", (source_id,)
    ).fetchone()
    if source is None:
        raise ValueError("Source not found.")
    url = source["canonical_url"]

    attempt_id = "fetch-" + uuid.uuid4().hex[:20]
    attempted_at = now_iso()
    response_status: int | None = None
    content_type: str | None = None
    byte_count = 0
    try:
        _validate_public_url(url)
        timeout = httpx.Timeout(timeout_seconds, connect=10.0)
        with httpx.Client(timeout=timeout, follow_redirects=False,
                          headers={"User-Agent": "CSDIS research source collector/0.1 (manual user-initiated request)"}) as client:
            current_url = url
            for redirect_count in range(6):
                _validate_public_url(current_url)
                with client.stream("GET", current_url) as response:
                    response_status = response.status_code
                    if response_status in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location or redirect_count == 5:
                            raise ValueError("Source redirected too many times or omitted a redirect destination.")
                        current_url = urljoin(current_url, location)
                        continue
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "application/octet-stream").split(";")[0]
                    declared_size = response.headers.get("content-length")
                    if declared_size and int(declared_size) > max_bytes:
                        raise ValueError(f"Source exceeds the {max_bytes // (1024 * 1024)} MiB download limit.")
                    chunks: list[bytes] = []
                    for chunk in response.iter_bytes():
                        byte_count += len(chunk)
                        if byte_count > max_bytes:
                            raise ValueError(f"Source exceeded the {max_bytes // (1024 * 1024)} MiB download limit.")
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    filename = Path(urlparse(str(response.url)).path).name or f"{source_id}_download"
                    break
            else:
                raise ValueError("Source exceeded the redirect limit.")
        version_id, created, path = store_source_version(
            connection, raw_root, source_id, filename, content, content_type,
            retrieval_method="public_http_download", http_status=response_status,
        )
        connection.execute(
            """INSERT INTO source_fetch_attempts (attempt_id, source_id, requested_url, attempted_at,
               outcome, http_status, content_type, bytes_received) VALUES (?, ?, ?, ?, 'success', ?, ?, ?)""",
            (attempt_id, source_id, url, attempted_at, response_status, content_type, byte_count),
        )
        audit(connection, "source_download_succeeded", "source", source_id,
              {"source_version_id": version_id, "http_status": response_status, "bytes": byte_count})
        connection.commit()
        return version_id, created, path, response_status or 0
    except Exception as exc:
        connection.execute(
            """INSERT INTO source_fetch_attempts (attempt_id, source_id, requested_url, attempted_at,
               outcome, http_status, content_type, bytes_received, error_message)
               VALUES (?, ?, ?, ?, 'failed', ?, ?, ?, ?)""",
            (attempt_id, source_id, url, attempted_at, response_status, content_type, byte_count, str(exc)),
        )
        audit(connection, "source_download_failed", "source", source_id,
              {"http_status": response_status, "bytes_received": byte_count, "error": str(exc)})
        connection.commit()
        raise


def verify_source_version(connection: sqlite3.Connection, raw_root: Path, source_version_id: str) -> tuple[bool, str]:
    """Recompute the stored file hash and audit the integrity check."""
    row = connection.execute(
        "SELECT storage_path, sha256 FROM source_versions WHERE source_version_id=?",
        (source_version_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Source version not found.")
    path = raw_root / row["storage_path"]
    if not path.is_file():
        actual = "missing"
        valid = False
    else:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        actual = digest.hexdigest()
        valid = actual == row["sha256"]
    audit(connection, "source_version_checksum_checked", "source_version", source_version_id,
          {"expected_sha256": row["sha256"], "actual_sha256": actual, "valid": valid})
    connection.commit()
    return valid, actual
