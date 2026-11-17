"""Matrix importer: preflight blocks partial imports, rows land as Proposed, re-runs are idempotent."""

import importlib.util
from pathlib import Path

import pytest

from csdis.database import connect, now_iso
from tests.test_coverage import _seed

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("import_coverage_matrix", ROOT / "tools" / "import_coverage_matrix.py")
importer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(importer)


@pytest.fixture
def conn(tmp_path: Path):
    connection = connect(tmp_path / "import.sqlite3")
    _seed(connection)
    connection.execute(
        """INSERT INTO technology_modules (technology_id, evidence_id, system_name, module_name, function_raw,
           detection_mode, deployment_status, project_condition, limitations, review_status, created_at)
           VALUES ('tech-mom-construction-vss', 'ev-tech', 'VSS', 'Recording', 'Records', 'Passive record',
                   'Mandated', '', '', 'Human-verified', ?)""", (now_iso(),))
    connection.commit()
    yield connection
    connection.close()


def _row(**overrides) -> dict[str, str]:
    row = dict(row_id="cov25-002", system="SG VSS", hazard_dimension="Accident type",
               hazard_label_raw="Slip, Trip or Fall On Same Level", hazard_evidence_id="ev-hazard",
               technology_evidence_id="ev-tech", coverage_class="Indirect", coverage_scope="",
               coverage_rationale="Recorded only at listed locations.", automation_level="Passive recording",
               policy_status="Mandatory at listed locations.", coder_confidence="Medium", deployment_evidence="Unknown",
               human_action="", open_list="", adjudication="", coder_status="Independently coded (agreed)")
    row.update(overrides)
    return row


def test_imports_as_proposed_with_context_and_is_idempotent(conn):
    assert importer.import_rows(conn, [_row(coverage_scope="Partial")]) == 1
    saved = conn.execute("SELECT * FROM coverage_mappings WHERE mapping_id='cov25-002'").fetchone()
    assert saved["coder_status"] == "Proposed" and saved["technology_id"] == "tech-mom-construction-vss"
    assert "Scope: Partial" in saved["coverage_rationale"]
    assert "Source matrix status: Independently coded (agreed)" in saved["coverage_rationale"]
    assert importer.import_rows(conn, [_row(coverage_scope="Partial")]) == 0


def test_preflight_rejects_whole_batch_if_any_row_is_unverified(conn):
    with pytest.raises(ValueError, match="cov25-004: hazard evidence ev-unreviewed"):
        importer.import_rows(conn, [_row(), _row(row_id="cov25-004", hazard_evidence_id="ev-unreviewed")])
    assert conn.execute("SELECT COUNT(*) FROM coverage_mappings").fetchone()[0] == 0


def test_conflicting_existing_mapping_is_refused(conn):
    importer.import_rows(conn, [_row()])
    with pytest.raises(ValueError, match="conflicts"):
        importer.import_rows(conn, [_row(hazard_label_raw="Different label")])
