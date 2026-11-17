"""SQLite persistence and audit helpers for the local MVP."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sources (
  source_id TEXT PRIMARY KEY,
  publisher TEXT NOT NULL,
  title TEXT NOT NULL,
  source_type TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  format TEXT NOT NULL,
  authority_tier TEXT NOT NULL,
  frequency TEXT NOT NULL DEFAULT '',
  data_period TEXT NOT NULL DEFAULT '',
  expected_data TEXT NOT NULL DEFAULT '',
  verification_notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  origin TEXT NOT NULL DEFAULT 'manual'
);
CREATE TABLE IF NOT EXISTS source_versions (
  source_version_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  version_label TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  file_size INTEGER NOT NULL,
  content_type TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  retrieval_method TEXT NOT NULL,
  http_status INTEGER,
  UNIQUE(source_id, sha256)
);
CREATE TABLE IF NOT EXISTS source_fetch_attempts (
  attempt_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  requested_url TEXT NOT NULL,
  attempted_at TEXT NOT NULL,
  outcome TEXT NOT NULL,
  http_status INTEGER,
  content_type TEXT,
  bytes_received INTEGER,
  error_message TEXT
);
CREATE TABLE IF NOT EXISTS evidence (
  evidence_id TEXT PRIMARY KEY,
  source_version_id TEXT NOT NULL REFERENCES source_versions(source_version_id),
  page_or_section TEXT NOT NULL,
  exact_quote_or_excerpt TEXT NOT NULL,
  locator_type TEXT NOT NULL,
  extraction_method TEXT NOT NULL,
  review_status TEXT NOT NULL,
  reviewer TEXT,
  confidence TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extracted_table_rows (
  row_id TEXT PRIMARY KEY,
  source_version_id TEXT NOT NULL REFERENCES source_versions(source_version_id),
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  page_number INTEGER NOT NULL,
  table_index INTEGER NOT NULL,
  row_index INTEGER NOT NULL,
  raw_cells_json TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'Unreviewed',
  reviewer TEXT,
  review_note TEXT,
  extracted_at TEXT NOT NULL,
  UNIQUE(source_version_id, page_number, table_index, row_index)
);
CREATE TABLE IF NOT EXISTS metrics (
  metric_id TEXT PRIMARY KEY,
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  jurisdiction TEXT NOT NULL,
  sector_or_cohort TEXT NOT NULL,
  period_start TEXT NOT NULL,
  period_end TEXT NOT NULL,
  metric_label_raw TEXT NOT NULL,
  metric_label_harmonised TEXT,
  classification_dimension TEXT NOT NULL,
  numerator REAL,
  denominator REAL,
  denominator_definition TEXT NOT NULL,
  raw_value TEXT NOT NULL,
  numeric_value REAL,
  unit TEXT NOT NULL,
  rate_multiplier REAL,
  formula TEXT,
  outcome_definition TEXT,
  comparability_status TEXT NOT NULL DEFAULT 'Unassessed',
  comparability_note TEXT,
  verification_status TEXT NOT NULL,
  reviewer TEXT,
  review_note TEXT,
  reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS conflicts (
  conflict_id TEXT PRIMARY KEY,
  metric_a_id TEXT NOT NULL REFERENCES metrics(metric_id),
  metric_b_id TEXT NOT NULL REFERENCES metrics(metric_id),
  severity TEXT NOT NULL,
  status TEXT NOT NULL,
  description TEXT NOT NULL,
  created_at TEXT NOT NULL,
  reviewer TEXT,
  resolution_note TEXT
);
CREATE TABLE IF NOT EXISTS policy_events (
  policy_id TEXT PRIMARY KEY,
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  jurisdiction TEXT NOT NULL,
  instrument TEXT NOT NULL,
  announcement_date TEXT,
  effective_from TEXT,
  effective_to TEXT,
  project_threshold TEXT NOT NULL,
  currency TEXT NOT NULL,
  covered_project_type TEXT NOT NULL,
  mandatory_status TEXT NOT NULL,
  requirement_text TEXT NOT NULL,
  supersedes_policy_id TEXT,
  review_status TEXT NOT NULL DEFAULT 'Unreviewed',
  reviewer TEXT,
  review_note TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS technology_modules (
  technology_id TEXT PRIMARY KEY,
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  system_name TEXT NOT NULL,
  module_name TEXT NOT NULL,
  function_raw TEXT NOT NULL,
  detection_mode TEXT NOT NULL,
  deployment_status TEXT NOT NULL,
  project_condition TEXT NOT NULL,
  limitations TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'Unreviewed',
  reviewer TEXT,
  review_note TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS coverage_mappings (
  mapping_id TEXT PRIMARY KEY,
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  technology_id TEXT NOT NULL REFERENCES technology_modules(technology_id),
  hazard_dimension TEXT NOT NULL,
  hazard_label_raw TEXT NOT NULL,
  hazard_label_harmonised TEXT,
  coverage_class TEXT NOT NULL,
  coverage_rationale TEXT NOT NULL,
  automation_level TEXT NOT NULL,
  coder_status TEXT NOT NULL DEFAULT 'Proposed',
  coder TEXT NOT NULL,
  reviewer TEXT,
  reviewer_notes TEXT NOT NULL DEFAULT '',
  reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS literature_searches (
  query_id TEXT PRIMARY KEY,
  database_name TEXT NOT NULL,
  query_text TEXT NOT NULL,
  searched_at TEXT NOT NULL,
  result_count INTEGER NOT NULL DEFAULT 0,
  page_size INTEGER NOT NULL,
  filters_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL,
  error_message TEXT
);
CREATE TABLE IF NOT EXISTS literature_records (
  record_id TEXT PRIMARY KEY,
  doi TEXT,
  title TEXT NOT NULL,
  authors TEXT NOT NULL,
  year INTEGER,
  venue TEXT,
  database_name TEXT NOT NULL,
  query_id TEXT NOT NULL REFERENCES literature_searches(query_id),
  external_id TEXT,
  record_url TEXT,
  screening_status TEXT NOT NULL DEFAULT 'Unscreened',
  exclusion_reason TEXT,
  full_text_status TEXT NOT NULL DEFAULT 'Metadata only',
  duplicate_status TEXT NOT NULL DEFAULT 'No duplicate detected',
  duplicate_of TEXT,
  reviewer TEXT,
  review_note TEXT,
  imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS literature_full_texts (
  file_id TEXT PRIMARY KEY,
  record_id TEXT NOT NULL REFERENCES literature_records(record_id),
  storage_path TEXT NOT NULL,
  original_filename TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  file_size INTEGER NOT NULL,
  content_type TEXT NOT NULL,
  source_kind TEXT NOT NULL DEFAULT 'User upload',
  added_at TEXT NOT NULL,
  UNIQUE(record_id, sha256)
);
CREATE TABLE IF NOT EXISTS audit_events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS seed_import_errors (
  error_id INTEGER PRIMARY KEY AUTOINCREMENT,
  imported_at TEXT NOT NULL,
  row_number INTEGER NOT NULL,
  source_id TEXT,
  error TEXT NOT NULL,
  raw_row_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_versions_source ON source_versions(source_id);
CREATE INDEX IF NOT EXISTS idx_fetch_source ON source_fetch_attempts(source_id, attempted_at);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_evidence_version ON evidence(source_version_id);
CREATE INDEX IF NOT EXISTS idx_table_rows_version ON extracted_table_rows(source_version_id);
CREATE INDEX IF NOT EXISTS idx_metrics_period ON metrics(period_start, period_end);
CREATE INDEX IF NOT EXISTS idx_policy_scope ON policy_events(jurisdiction, effective_from);
CREATE INDEX IF NOT EXISTS idx_tech_system ON technology_modules(system_name, module_name);
CREATE INDEX IF NOT EXISTS idx_mapping_hazard ON coverage_mappings(hazard_dimension, hazard_label_raw);
CREATE INDEX IF NOT EXISTS idx_literature_doi ON literature_records(doi);
CREATE INDEX IF NOT EXISTS idx_literature_query ON literature_records(query_id);
CREATE INDEX IF NOT EXISTS idx_literature_full_text_record ON literature_full_texts(record_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Create a SQLite connection and ensure schema exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # Streamlit reruns can execute on a different script thread while the
    # cached connection remains alive. The app is a local, single-user tool;
    # disable sqlite's creator-thread guard so those reruns can reuse it.
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    metric_columns = {row["name"] for row in connection.execute("PRAGMA table_info(metrics)")}
    for name, definition in (("reviewer", "TEXT"), ("review_note", "TEXT"), ("reviewed_at", "TEXT")):
        if name not in metric_columns:
            connection.execute(f"ALTER TABLE metrics ADD COLUMN {name} {definition}")
    metric_columns = {row["name"] for row in connection.execute("PRAGMA table_info(metrics)")}
    for name, definition in (("rate_multiplier", "REAL"), ("formula", "TEXT"), ("metric_label_harmonised", "TEXT"),
                             ("outcome_definition", "TEXT"),
                             ("comparability_status", "TEXT NOT NULL DEFAULT 'Unassessed'"),
                             ("comparability_note", "TEXT")):
        if name not in metric_columns:
            connection.execute(f"ALTER TABLE metrics ADD COLUMN {name} {definition}")
    table_row_columns = {row["name"] for row in connection.execute("PRAGMA table_info(extracted_table_rows)")}
    if "evidence_id" not in table_row_columns:
        connection.execute("ALTER TABLE extracted_table_rows ADD COLUMN evidence_id TEXT REFERENCES evidence(evidence_id)")
    connection.commit()
    return connection


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def audit(
    connection: sqlite3.Connection,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any] | None = None,
    actor: str = "local-user",
) -> None:
    """Append an immutable event describing a researcher-visible action."""
    connection.execute(
        "INSERT INTO audit_events (occurred_at, actor, action, entity_type, entity_id, details_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (now_iso(), actor, action, entity_type, entity_id, json.dumps(details or {}, ensure_ascii=False)),
    )


def table_count(connection: sqlite3.Connection, table: str) -> int:
    allowed = {"sources", "source_versions", "source_fetch_attempts", "evidence", "extracted_table_rows", "metrics", "conflicts", "policy_events", "technology_modules", "coverage_mappings", "literature_searches", "literature_records", "literature_full_texts", "audit_events", "seed_import_errors"}
    if table not in allowed:
        raise ValueError(f"Unsupported table: {table}")
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
