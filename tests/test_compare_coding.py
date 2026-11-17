"""Tests for the inter-coder comparison tool."""

import csv
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("compare_coding", ROOT / "tools" / "compare_coding.py")
compare_coding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compare_coding)

FIELDS = ["row_id", "system", "hazard_dimension", "hazard_label_raw", "count_2025", "coverage_class",
          "coverage_scope", "matched_functions", "automation_level", "coverage_rationale", "coder_confidence"]


def test_kappa_matches_known_value():
    # Classic 2x2 example: 50 items, po = 0.7, pe = 0.5 -> kappa = 0.4
    a = ["Yes"] * 25 + ["No"] * 25
    b = ["Yes"] * 20 + ["No"] * 5 + ["Yes"] * 10 + ["No"] * 15
    assert compare_coding.cohen_kappa(a, b) == pytest.approx(0.4)
    assert compare_coding.cohen_kappa(["A", "B"], ["A", "B"]) == pytest.approx(1.0)


def _write(path: Path, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def _row(rid, system, cls, scope="", functions=""):
    return {"row_id": rid, "system": system, "hazard_dimension": "Agent", "hazard_label_raw": f"label {rid}",
            "count_2025": "1", "coverage_class": cls, "coverage_scope": scope, "matched_functions": functions,
            "automation_level": "Sensor alert" if cls == "Direct" else "", "coverage_rationale": "because",
            "coder_confidence": "High"}


def test_compare_reports_and_exports_disagreements(tmp_path: Path, capsys):
    a = [_row("r1", "HK 4S", "Direct", "Full", "x [cl.5(12)(e)]"), _row("r2", "HK 4S", "Indirect"),
         _row("r3", "SG VSS", "Indirect"), _row("r4", "SG VSS", "Uncertain")]
    b = [_row("r1", "HK 4S", "Direct", "Partial", "5(12)(e)"), _row("r2", "HK 4S", "Indirect"),
         _row("r3", "SG VSS", "No documented coverage"), _row("r4", "SG VSS", "Uncertain")]
    _write(tmp_path / "a.csv", a)
    _write(tmp_path / "b.csv", b)
    out = tmp_path / "dis.csv"
    assert compare_coding.main([str(tmp_path / "a.csv"), str(tmp_path / "b.csv"), "--out", str(out)]) == 0
    report = capsys.readouterr().out
    assert "class agreement 3/4" in report
    assert "Scope agreement where both chose Direct: 0/1" in report
    assert "common clause: 1/1" in report
    flagged = [r["row_id"] for r in csv.DictReader(open(out, encoding="utf-8-sig"))]
    assert flagged == ["r1", "r3"]


def test_invalid_values_block_comparison(tmp_path: Path, capsys):
    bad = _row("r1", "HK 4S", "direct")  # wrong case
    _write(tmp_path / "a.csv", [_row("r1", "HK 4S", "Indirect")])
    _write(tmp_path / "b.csv", [bad])
    assert compare_coding.main([str(tmp_path / "a.csv"), str(tmp_path / "b.csv")]) == 1
    assert "not one of" in capsys.readouterr().out


def test_draft_matrix_passes_validation():
    rows = compare_coding.load(str(ROOT / "CSDIS_Coverage_Matrix_2025_DRAFT.csv"))
    assert len(rows) == 148
    assert compare_coding.validate(rows, "draft") == []


def test_apply_adjudication_changes_class_and_copies_evidence(tmp_path: Path):
    spec2 = importlib.util.spec_from_file_location("apply_adjudication", ROOT / "tools" / "apply_adjudication.py")
    apply_adjudication = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(apply_adjudication)
    base = {"hazard_dimension": "Agent", "count_2025": "1", "coverage_scope": "", "coverage_rationale": "r",
            "technology_evidence_id": "", "technology_locator": "", "matched_functions": "", "automation_level": "",
            "coder_confidence": "High", "coder": "", "coder_status": "Proposed", "human_action": ""}
    rows = [dict(base, row_id="cov25-001", system="HK 4S", coverage_class="Indirect", technology_evidence_id="ev-cam",
                 matched_functions="cameras", automation_level="Passive recording"),
            dict(base, row_id="cov25-019", system="HK 4S", coverage_class="No documented coverage"),
            dict(base, row_id="cov25-131", system="HK 4S", coverage_class="No documented coverage")]
    matrix = tmp_path / "m.csv"
    with open(matrix, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    adj = tmp_path / "a.csv"
    with open(adj, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["row_id", "final_class", "final_scope", "rule", "final_rationale",
                                          "final_open_list", "proposal_confidence"])
        w.writeheader()
        w.writerow({"row_id": "cov25-131", "final_class": "Indirect", "final_scope": "", "rule": "R4",
                    "final_rationale": "visible", "final_open_list": "", "proposal_confidence": "Low"})
    assert apply_adjudication.main([str(matrix), str(adj)]) == 0
    out = {r["row_id"]: r for r in csv.DictReader(open(matrix, encoding="utf-8-sig"))}
    assert out["cov25-131"]["coverage_class"] == "Indirect"
    assert out["cov25-131"]["technology_evidence_id"] == "ev-cam"
    assert out["cov25-131"]["coder_status"] == "Adjudicated"
    assert out["cov25-001"]["coder_status"] == "Independently coded (agreed)"
