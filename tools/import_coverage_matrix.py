"""Import the reviewed 2025 coverage matrix as Proposed CSDIS mappings.

The CSV contains coder-facing scope and policy fields that the current CSDIS
schema does not expose separately. Those fields are retained in the rationale
so the import remains reviewable and no matrix context is silently discarded.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from csdis.coverage import propose_coverage_mapping
from csdis.database import connect
from csdis.schemas import CoverageMapping


DEFAULT_CSV = ROOT / "CSDIS_Coverage_Matrix_2025.csv"
DEFAULT_DB = ROOT / "data" / "local" / "csdis.sqlite3"

MODULES = {
    ("HK 4S", "Passive recording"): "tech-hk-4s-camera-recording",
    ("HK 4S", "Sensor alert"): "tech-hk-4s-sensor-alerts",
    ("HK 4S", "Tracking"): "tech-hk-4s-tracking",
    ("HK 4S", "AI detection"): "tech-hk-4s-annex-a",
    ("HK 4S", "Manual review"): "tech-hk-4s-human-review",
    ("SG VSS", "Passive recording"): "tech-mom-construction-vss",
    ("SG VSS", "Manual review"): "tech-mom-construction-vss",
}


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 148:
        raise ValueError(f"Expected 148 matrix rows; found {len(rows)}.")
    return rows


def full_rationale(row: dict[str, str]) -> str:
    parts = [row["coverage_rationale"].strip()]
    for field, label in (
        ("coverage_scope", "Scope"), ("policy_status", "Policy status"),
        ("coder_confidence", "Coder confidence"), ("deployment_evidence", "Deployment evidence"),
        ("human_action", "Human action"), ("open_list", "Open list"),
        ("adjudication", "Adjudication note"),
    ):
        value = row.get(field, "").strip()
        if value:
            parts.append(f"{label}: {value}")
    parts.append("Source matrix status: " + row["coder_status"].strip())
    return "\n".join(parts)


def import_rows(conn: sqlite3.Connection, rows: list[dict[str, str]]) -> int:
    """Check every row, then add those not yet stored as Proposed mappings. Returns the number added."""
    missing = []
    for row in rows:
        tech_id = MODULES.get((row["system"], row["automation_level"]))
        if not tech_id:
            missing.append(f"{row['row_id']}: unsupported system/mode {row['system']}/{row['automation_level']}")
            continue
        for evidence_id, role in ((row["hazard_evidence_id"], "hazard"),
                                  (row["technology_evidence_id"], "technology")):
            evidence = conn.execute("SELECT review_status FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
            if not evidence or evidence["review_status"] != "Human-verified":
                missing.append(f"{row['row_id']}: {role} evidence {evidence_id} is absent or unverified")
        module = conn.execute("SELECT review_status FROM technology_modules WHERE technology_id=?", (tech_id,)).fetchone()
        if not module or module["review_status"] != "Human-verified":
            missing.append(f"{row['row_id']}: module {tech_id} is absent or unverified")
    if missing:
        raise ValueError("Preflight failed; no rows imported:\n" + "\n".join(missing))

    existing = {r["mapping_id"]: dict(r) for r in conn.execute("SELECT * FROM coverage_mappings")}
    added = 0
    for row in rows:
        mapping_id = row["row_id"]
        tech_id = MODULES[(row["system"], row["automation_level"])]
        if mapping_id in existing:
            saved = existing[mapping_id]
            if (saved["technology_id"], saved["hazard_evidence_id"], saved["technology_evidence_id"],
                saved["hazard_label_raw"], saved["automation_level"]) != (
                tech_id, row["hazard_evidence_id"], row["technology_evidence_id"],
                row["hazard_label_raw"], row["automation_level"]):
                raise ValueError(f"Existing mapping {mapping_id} conflicts with this CSV.")
            continue
        propose_coverage_mapping(conn, CoverageMapping(
            mapping_id=mapping_id,
            hazard_evidence_id=row["hazard_evidence_id"],
            technology_evidence_id=row["technology_evidence_id"],
            technology_id=tech_id,
            hazard_dimension=row["hazard_dimension"],
            hazard_label_raw=row["hazard_label_raw"],
            coverage_class=row["coverage_class"],
            coverage_rationale=full_rationale(row),
            automation_level=row["automation_level"],
            coder="Coder A",
        ))
        added += 1
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    rows = load_rows(args.csv)
    conn = connect(args.db)
    try:
        added = import_rows(conn, rows)
        print(f"Imported {added} new mappings as Proposed; {len(rows)-added} matching rows already existed.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
