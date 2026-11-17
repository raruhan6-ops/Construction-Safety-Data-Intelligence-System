"""Screening sheet: export labels search sets, import validates, dry-runs by default and audits each decision."""

import csv
import importlib.util
from pathlib import Path

import pytest

from csdis.database import connect, now_iso

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("screening_sheet", ROOT / "tools" / "literature_screening_sheet.py")
sheet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sheet)


@pytest.fixture
def conn(tmp_path: Path):
    c = connect(tmp_path / "lit.sqlite3")
    ts = now_iso()
    c.execute("""INSERT INTO literature_searches (query_id, database_name, query_text, searched_at, page_size,
                 filters_json, status) VALUES ('q-main', 'OpenAlex', 'a AND b', ?, 50,
                 '{"filter": "title_and_abstract.search:a AND b"}', 'Completed')""", (ts,))
    c.execute("""INSERT INTO literature_searches (query_id, database_name, query_text, searched_at, page_size,
                 status) VALUES ('q-kw', 'Crossref', 'a b', ?, 50, 'Completed')""", (ts,))
    for rid, qid, dup, dup_of in (("r1", "q-main", "No duplicate detected", None),
                                  ("r2", "q-main", "Potential DOI duplicate", "r1"),
                                  ("r3", "q-kw", "No duplicate detected", None)):
        c.execute("""INSERT INTO literature_records (record_id, title, authors, database_name, query_id,
                     duplicate_status, duplicate_of, imported_at) VALUES (?, ?, 'X', 'OpenAlex', ?, ?, ?, ?)""",
                  (rid, f"Title {rid}", qid, dup, dup_of, ts))
    c.commit()
    yield c
    c.close()


def _read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _write(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sheet.FIELDS)
        w.writeheader()
        w.writerows(rows)


def test_export_labels_sets_and_duplicates(conn, tmp_path):
    out = tmp_path / "s.csv"
    assert sheet.export_sheet(conn, out, {"r1": "An abstract."}) == 3
    rows = {r["record_id"]: r for r in _read(out)}
    assert (rows["r1"]["source_set"], rows["r1"]["query"]) == ("Main search", "Q1")
    assert rows["r3"]["source_set"] == "Other sources"
    assert rows["r2"]["duplicate_of_title"] == "Title r1" and rows["r1"]["abstract"] == "An abstract."


def test_import_dry_run_then_apply_with_audit(conn, tmp_path):
    out = tmp_path / "s.csv"
    sheet.export_sheet(conn, out)
    rows = _read(out)
    for r in rows:
        if r["record_id"] == "r1":
            r["decision"] = "Include"
        elif r["record_id"] == "r2":
            r["dup_decision"] = "Confirmed duplicate"
        else:
            r["decision"], r["exclusion_reason"], r["note"] = "Exclude", "Not construction", "Mining study."
    _write(out, rows)
    tally = sheet.import_sheet(conn, out, "Screener", apply=False)
    assert tally["changed"] == 3
    assert conn.execute("SELECT COUNT(*) FROM literature_records WHERE screening_status!='Unscreened'").fetchone()[0] == 0
    sheet.import_sheet(conn, out, "Screener", apply=True)
    saved = {r["record_id"]: r for r in conn.execute("SELECT * FROM literature_records")}
    assert saved["r1"]["screening_status"] == "Include" and saved["r1"]["reviewer"] == "Screener"
    assert saved["r2"]["duplicate_status"] == "Confirmed duplicate" and saved["r2"]["screening_status"] == "Unscreened"
    assert (saved["r3"]["exclusion_reason"], saved["r3"]["review_note"]) == ("Not construction", "Mining study.")
    assert conn.execute("SELECT COUNT(*) FROM audit_events WHERE action='literature_screening_updated'").fetchone()[0] == 3
    assert sheet.import_sheet(conn, out, "Screener", apply=True)["changed"] == 0


def test_import_rejects_bad_rows_without_writing(conn, tmp_path):
    out = tmp_path / "s.csv"
    sheet.export_sheet(conn, out)
    rows = _read(out)
    rows[0]["decision"] = "Include"
    rows[1]["decision"] = "Exclude"  # no reason
    _write(out, rows)
    with pytest.raises(ValueError, match="needs an exclusion_reason"):
        sheet.import_sheet(conn, out, "Screener", apply=True)
    assert conn.execute("SELECT COUNT(*) FROM literature_records WHERE screening_status!='Unscreened'").fetchone()[0] == 0
    with pytest.raises(ValueError, match="reviewer"):
        sheet.import_sheet(conn, out, " ", apply=True)
