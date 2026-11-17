"""Coverage mappings: role-specific evidence links, review rules and legacy migration."""

import sqlite3
from pathlib import Path

import pytest

from csdis.coverage import CoverageError, propose_coverage_mapping, review_coverage_mapping, set_mapping_evidence
from csdis.database import connect, now_iso
from csdis.schemas import CoverageMapping


def _seed(connection: sqlite3.Connection) -> None:
    ts = now_iso()
    connection.execute(
        """INSERT INTO sources (source_id, publisher, title, source_type, canonical_url, format, authority_tier,
           created_at, updated_at) VALUES ('S1', 'Pub', 'Title', 'Stats', 'https://public.example/a.pdf', 'PDF',
           'Primary', ?, ?)""", (ts, ts))
    connection.execute(
        """INSERT INTO source_versions (source_version_id, source_id, version_label, original_filename,
           storage_path, sha256, file_size, content_type, retrieved_at, retrieval_method)
           VALUES ('V1', 'S1', 'v1', 'f.pdf', 'x', 'abc', 1, 'application/pdf', ?, 'upload')""", (ts,))
    for evidence_id, status in (("ev-hazard", "Human-verified"), ("ev-tech", "Human-verified"),
                                ("ev-unreviewed", "Unreviewed")):
        connection.execute(
            """INSERT INTO evidence (evidence_id, source_version_id, page_or_section, exact_quote_or_excerpt,
               locator_type, extraction_method, review_status, confidence, created_at)
               VALUES (?, 'V1', 'p1', 'text', 'page', 'test', ?, 'High', ?)""", (evidence_id, status, ts))
    connection.execute(
        """INSERT INTO technology_modules (technology_id, evidence_id, system_name, module_name, function_raw,
           detection_mode, deployment_status, project_condition, limitations, review_status, created_at)
           VALUES ('tech-1', 'ev-tech', 'Sys', 'Alert', 'Alerts', 'Sensor threshold', 'Mandated', '', '',
                   'Human-verified', ?)""", (ts,))
    connection.commit()


@pytest.fixture
def conn(tmp_path: Path):
    connection = connect(tmp_path / "coverage.sqlite3")
    _seed(connection)
    yield connection
    connection.close()


def _mapping(**overrides) -> CoverageMapping:
    values = dict(mapping_id="mapping-1", hazard_evidence_id="ev-hazard", technology_evidence_id="ev-tech",
                  technology_id="tech-1", hazard_dimension="Unsafe condition", hazard_label_raw="Danger zone",
                  coverage_class="Direct", coverage_rationale="Spec requires alerts.", automation_level="Sensor alert",
                  coder="A")
    values.update(overrides)
    return CoverageMapping(**values)


def test_mapping_stores_both_evidence_roles(conn):
    propose_coverage_mapping(conn, _mapping())
    row = conn.execute("SELECT * FROM coverage_mappings WHERE mapping_id='mapping-1'").fetchone()
    assert (row["hazard_evidence_id"], row["technology_evidence_id"]) == ("ev-hazard", "ev-tech")
    assert row["coder_status"] == "Proposed" and row["legacy_evidence_id"] is None


def test_schema_requires_both_roles():
    with pytest.raises(ValueError):
        CoverageMapping(mapping_id="m", technology_evidence_id="ev-tech", technology_id="tech-1",
                        hazard_dimension="Agent", hazard_label_raw="x", coverage_class="Direct",
                        coverage_rationale="r", automation_level="Sensor alert", coder="A")


def test_unreviewed_evidence_and_incompatible_automation_rejected(conn):
    with pytest.raises(CoverageError, match="Hazard evidence"):
        propose_coverage_mapping(conn, _mapping(hazard_evidence_id="ev-unreviewed"))
    with pytest.raises(CoverageError, match="conflicts"):
        propose_coverage_mapping(conn, _mapping(automation_level="AI detection"))
    assert conn.execute("SELECT COUNT(*) FROM coverage_mappings").fetchone()[0] == 0


def test_review_chain_enforces_independence_and_order(conn):
    propose_coverage_mapping(conn, _mapping())
    with pytest.raises(CoverageError, match="differ"):
        review_coverage_mapping(conn, "mapping-1", "Independently coded", " a ", "same coder")
    with pytest.raises(CoverageError, match="Cannot move"):
        review_coverage_mapping(conn, "mapping-1", "Locked", "B", "skip ahead")
    for status in ("Independently coded", "Adjudicated", "Locked"):
        review_coverage_mapping(conn, "mapping-1", status, "B", "ok")
    assert conn.execute("SELECT coder_status FROM coverage_mappings").fetchone()[0] == "Locked"
    with pytest.raises(CoverageError, match="Locked"):
        set_mapping_evidence(conn, "mapping-1", "ev-hazard", "ev-tech", "B", "late change")


def test_legacy_single_evidence_schema_is_migrated_without_inferring_roles(tmp_path: Path):
    db_path = tmp_path / "legacy.sqlite3"
    connection = connect(db_path)
    _seed(connection)
    # Recreate the pre-split table shape and a legacy row.
    connection.executescript("""
        DROP TABLE coverage_mappings;
        CREATE TABLE coverage_mappings (
          mapping_id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
          technology_id TEXT NOT NULL REFERENCES technology_modules(technology_id),
          hazard_dimension TEXT NOT NULL, hazard_label_raw TEXT NOT NULL, hazard_label_harmonised TEXT,
          coverage_class TEXT NOT NULL, coverage_rationale TEXT NOT NULL, automation_level TEXT NOT NULL,
          coder_status TEXT NOT NULL DEFAULT 'Proposed', coder TEXT NOT NULL, reviewer TEXT,
          reviewer_notes TEXT NOT NULL DEFAULT '', reviewed_at TEXT);
        INSERT INTO coverage_mappings (mapping_id, evidence_id, technology_id, hazard_dimension, hazard_label_raw,
          coverage_class, coverage_rationale, automation_level, coder, coder_status)
          VALUES ('old-1', 'ev-tech', 'tech-1', 'Agent', 'Crane', 'Direct', 'r', 'Sensor alert', 'A',
                  'Independently coded');
    """)
    connection.close()

    connection = connect(db_path)
    row = connection.execute("SELECT * FROM coverage_mappings WHERE mapping_id='old-1'").fetchone()
    assert row["legacy_evidence_id"] == "ev-tech"
    assert row["hazard_evidence_id"] is None and row["technology_evidence_id"] is None
    assert row["coder_status"] == "Independently coded" and row["hazard_label_raw"] == "Crane"
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE action='coverage_evidence_split_migrated'").fetchone()[0] == 1

    with pytest.raises(CoverageError, match="Assign both"):
        review_coverage_mapping(connection, "old-1", "Adjudicated", "C", "adjudicate")
    set_mapping_evidence(connection, "old-1", "ev-hazard", "ev-tech", "C", "Hazard from appendix L; tech from spec")
    review_coverage_mapping(connection, "old-1", "Adjudicated", "C", "adjudicate")
    connection.close()

    # A second connect must be a no-op.
    connection = connect(db_path)
    assert connection.execute(
        "SELECT COUNT(*) FROM audit_events WHERE action='coverage_evidence_split_migrated'").fetchone()[0] == 1
    connection.close()
