"""Second-screener sample: fixed-seed, decision-free, not importable; compare reports agreement and kappa."""

import importlib.util
from pathlib import Path

import pytest
from openpyxl import load_workbook

from csdis.database import connect, now_iso

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("screening_agreement", ROOT / "tools" / "screening_agreement.py")
agree = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agree)


@pytest.fixture
def conn(tmp_path: Path):
    c = connect(tmp_path / "lit.sqlite3")
    ts = now_iso()
    c.execute("""INSERT INTO literature_searches (query_id, database_name, query_text, searched_at, page_size,
                 filters_json, status) VALUES ('q', 'OpenAlex', 'a AND b', ?, 50,
                 '{"filter": "title_and_abstract.search:a AND b"}', 'Completed')""", (ts,))
    for i in range(10):
        c.execute("""INSERT INTO literature_records (record_id, title, authors, database_name, query_id,
                     duplicate_status, imported_at) VALUES (?, ?, 'X', 'OpenAlex', 'q', 'No duplicate detected', ?)""",
                  (f"r{i}", f"Title {i}", ts))
    c.commit()
    yield c
    c.close()


def _fill(path, decisions):
    wb = load_workbook(path)
    ws = wb[agree.TAB]
    header = [c.value for c in ws[1]]
    col = {h: i + 1 for i, h in enumerate(header)}
    for r in range(2, ws.max_row + 1):
        rid = ws.cell(r, 1).value
        if rid in decisions:
            d, reason = decisions[rid]
            ws.cell(r, col["decision"], d)
            ws.cell(r, col["exclusion_reason"], reason)
    wb.save(path)


def test_sample_is_reproducible_blank_and_not_importable(conn, tmp_path):
    a = agree.write_sample(conn, tmp_path / "a.xlsx", 0.5, 7, None)
    b = agree.write_sample(conn, tmp_path / "b.xlsx", 0.5, 7, None)
    assert a == b and len(a) == 5
    assert (tmp_path / "a_manifest.csv").exists()
    with pytest.raises(FileExistsError):
        agree.write_sample(conn, tmp_path / "a.xlsx", 0.5, 7, None)
    rows = agree.read_second(tmp_path / "a.xlsx")
    assert all(r["decision"] == "" for r in rows.values())
    with pytest.raises(KeyError):  # the normal import looks for the "Screening" tab
        agree.sheet.import_sheet(conn, tmp_path / "a.xlsx", "Screener", apply=False)


def test_compare_reports_kappa_and_disagreements(conn, tmp_path):
    ids = agree.write_sample(conn, tmp_path / "s.xlsx", 0.4, 1, None)  # 4 records
    for rid, status in zip(ids, ("Include", "Exclude", "Exclude", "Maybe")):
        conn.execute("UPDATE literature_records SET screening_status=?, exclusion_reason=? WHERE record_id=?",
                     (status, "Not construction" if status == "Exclude" else None, rid))
    conn.commit()
    _fill(tmp_path / "s.xlsx", {ids[0]: ("Include", None), ids[1]: ("Exclude", "Not construction"),
                                ids[2]: ("Maybe", None), ids[3]: ("Maybe", None)})
    report = agree.compare(conn, tmp_path / "s.xlsx")
    assert report["compared"] == 4 and report["three_way"]["agree"] == 3
    assert report["binary"]["agree"] == 3
    assert [d[0] for d in report["disagreements"]] == [ids[2]]
    assert conn.execute("SELECT screening_status FROM literature_records WHERE record_id=?",
                        (ids[2],)).fetchone()[0] == "Exclude"  # compare never writes


def test_kappa_matches_known_value():
    a = ["Include"] * 20 + ["Exclude"] * 30
    b = ["Include"] * 15 + ["Exclude"] * 5 + ["Include"] * 10 + ["Exclude"] * 20
    assert agree.cohen_kappa(a, b) == pytest.approx(0.4, abs=1e-9)
