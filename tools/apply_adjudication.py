"""Apply a final adjudication file to the coverage matrix.

Usage (from the project root):

    python tools/apply_adjudication.py CSDIS_Coverage_Matrix_2025.csv coder_pack/returns/adjudication_XY_FINAL.csv

The adjudication CSV needs the columns row_id, final_class, final_scope, rule, final_rationale,
final_open_list and proposal_confidence. Rows listed there get the final class and scope and are marked
Adjudicated. Every other row is marked as agreed by both coders. When a class changes, the
function, automation and evidence fields are copied from a reference row that documents the same
kind of function, so each row still cites a stored technology excerpt. The matrix is rewritten in
place with two extra columns: open_list and adjudication.
"""
from __future__ import annotations

import csv
import sys

# Reference rows whose function/evidence fields describe the documented function behind a class.
TEMPLATES = {
    ("HK 4S", "Indirect"): "cov25-001",                # cl.5(12)(g)(i) site-wide cameras
    ("HK 4S", "No documented coverage"): "cov25-019",  # Annex A reviewed in full
    ("SG VSS", "Indirect"): "cov25-002",               # VSS listed locations
    ("SG VSS", "No documented coverage"): "cov25-020", # VSS recording only
}
ROW_TEMPLATES = {"cov25-095": "cov25-109"}  # Indirect via permit-to-work tracking, not cameras
COPY = ["matched_functions", "automation_level", "technology_evidence_id", "technology_locator"]
CODER = "Two coders (A: author, AI-assisted; B: independent)"
ACTION = "Verify hazard and technology evidence links in CSDIS before promoting to Locked."


def main(argv: list[str]) -> int:
    matrix_path, adjudication_path = argv
    with open(matrix_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames)
        rows = list(reader)
    by_id = {r["row_id"]: r for r in rows}
    reference = {k: dict(v) for k, v in by_id.items()}  # templates read from the pre-adjudication state
    with open(adjudication_path, encoding="utf-8-sig", newline="") as f:
        decisions = {d["row_id"]: d for d in csv.DictReader(f)}

    missing = set(decisions) - set(by_id)
    if missing:
        print(f"Unknown row IDs in adjudication: {sorted(missing)}")
        return 1
    for col in ("open_list", "adjudication"):
        if col not in fields:
            fields.append(col)

    changed = 0
    for row in rows:
        row["coder"] = CODER
        row["human_action"] = ACTION
        d = decisions.get(row["row_id"])
        if d is None:
            row["coder_status"] = "Independently coded (agreed)"
            row.setdefault("open_list", "")
            row.setdefault("adjudication", "")
            continue
        new_class, new_scope = d["final_class"], d["final_scope"]
        if new_class == "Direct" and not new_scope:
            print(f"{row['row_id']}: Direct requires a scope")
            return 1
        if new_class != row["coverage_class"]:
            template = ROW_TEMPLATES.get(row["row_id"]) or TEMPLATES.get((row["system"], new_class))
            if template is None:
                print(f"{row['row_id']}: no reference row for {row['system']} / {new_class}")
                return 1
            for col in COPY:
                row[col] = reference[template][col]
            row["coder_confidence"] = d.get("proposal_confidence") or row["coder_confidence"]
        if (new_class, new_scope) != (row["coverage_class"], row["coverage_scope"]):
            changed += 1
        row["coverage_class"], row["coverage_scope"] = new_class, new_scope
        row["coverage_rationale"] = d["final_rationale"]
        row["open_list"] = d.get("final_open_list", "")
        row["coder_status"] = "Adjudicated"
        row["adjudication"] = f"Consensus adjudication under codebook v1.2 ({d['rule']})"

    with open(matrix_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Applied {len(decisions)} adjudicated rows ({changed} changed class or scope) to {matrix_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
