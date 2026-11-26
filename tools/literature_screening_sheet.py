"""Screen the literature register in a spreadsheet, then record the decisions in CSDIS.

Usage (from the project root):

    python tools/literature_screening_sheet.py export screening_sheet.csv [--abstracts]
    python tools/literature_screening_sheet.py export-xlsx data/local/screening_batches [--batch-size 100]
    python tools/literature_screening_sheet.py import screening_sheet.csv --reviewer "Name"          # dry run
    python tools/literature_screening_sheet.py import screening_sheet.csv --reviewer "Name" --apply  # write
    python tools/literature_screening_sheet.py import data/local/screening_batches/*.xlsx --reviewer "Name" --apply

Fill in these columns of the exported sheet and leave everything else alone:

- dup_decision: Confirmed duplicate or Distinct record (only for rows flagged as possible duplicates);
- decision: Include, Exclude or Maybe;
- exclusion_reason: one of EXCLUSION_REASONS, required for Exclude;
- note: optional; when blank, the note records that the decision came from the sheet.

export-xlsx writes Excel workbooks of --batch-size records each, with dropdowns for those columns and
an Instructions tab. Abstracts come from --abstracts-from (default: the CSV sheet in data/local, if
present), so no network access is needed. import reads .csv and .xlsx files, one or more at a time.

The import is a dry run unless --apply is given. Each changed row is saved through
csdis.literature.review_literature_record, so it gets the same validation and audit entry as a
decision made in the app. Rows whose values already match the database are skipped.

--abstracts fetches abstracts from the public OpenAlex API (by OpenAlex ID or DOI). Nothing about
the user is sent.
"""
from __future__ import annotations

import argparse
import csv
import http.client
import json
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from csdis.database import connect
from csdis.literature import review_literature_record

DEFAULT_DB = ROOT / "data" / "local" / "csdis.sqlite3"
DEFAULT_CSV = ROOT / "data" / "local" / "literature_screening_sheet.csv"
SCREEN_TAB = "Screening"
EXCLUSION_REASONS = (
    "Not construction", "Not safety or health", "Technology or policy not relevant", "No hazard or policy link",
    "Not research or official source", "Not English", "Duplicate", "Full text unavailable",
)
DECISIONS = ("Include", "Exclude", "Maybe")
DUP_DECISIONS = ("Confirmed duplicate", "Distinct record")
DEFAULT_DUP = "No duplicate detected"
BATCH = 20  # OpenAlex IDs per request; small responses survive unstable connections
FIELDS = ["record_id", "source_set", "query", "duplicate_status", "duplicate_of", "duplicate_of_title",
          "dup_decision", "decision", "exclusion_reason", "note",
          "title", "year", "venue", "authors", "doi", "record_url", "abstract", "database_name"]


def _abstract(inverted: dict | None) -> str:
    if not inverted:
        return ""
    words = sorted((pos, word) for word, positions in inverted.items() for pos in positions)
    return " ".join(word for _, word in words)


def fetch_openalex_abstracts(records: list[dict]) -> dict[str, str]:
    """Return {record_id: abstract} for records found in OpenAlex by ID or DOI (BATCH per request)."""
    by_key: dict[str, list[str]] = {}
    for r in records:
        ext = r["external_id"] or ""
        if ext.startswith("https://openalex.org/W"):
            by_key.setdefault("openalex:" + ext.rsplit("/", 1)[1], []).append(r["record_id"])
        elif r["doi"]:
            by_key.setdefault("doi:" + r["doi"].lower(), []).append(r["record_id"])
    out: dict[str, str] = {}
    for kind in ("openalex", "doi"):
        keys = [k.split(":", 1)[1] for k in by_key if k.startswith(kind + ":")]
        for i in range(0, len(keys), BATCH):
            chunk = keys[i:i + BATCH]
            url = "https://api.openalex.org/works?" + urllib.parse.urlencode({
                "filter": f"{kind}:" + "|".join(chunk), "per-page": BATCH,
                "select": "id,doi,abstract_inverted_index"})
            req = urllib.request.Request(url, headers={"User-Agent": "csdis-literature-screening"})
            works = None
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(req, timeout=90) as resp:
                        works = json.load(resp)["results"]
                    break
                except (OSError, ValueError, http.client.HTTPException) as exc:  # timeouts, dropped or cut-off responses
                    print(f"  {kind} batch {i // BATCH + 1}: attempt {attempt + 1} failed ({exc})")
                    time.sleep(2 ** attempt)
            if works is None:
                print(f"  {kind} batch {i // BATCH + 1}: skipped; those abstracts stay blank")
                continue
            for w in works:
                key = ("openalex:" + w["id"].rsplit("/", 1)[1]) if kind == "openalex" else \
                      ("doi:" + (w.get("doi") or "").lower().removeprefix("https://doi.org/"))
                for record_id in by_key.get(key, []):
                    out[record_id] = _abstract(w.get("abstract_inverted_index"))
    return out


def _query_labels(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """Map query_id to (source set, label). Structured title/abstract queries are numbered Q1-Q6
    in the order of their first run; everything else counts as other sources."""
    labels: dict[str, tuple[str, str]] = {}
    structured: dict[str, str] = {}
    for qid, db, text, filters in conn.execute(
            "SELECT query_id, database_name, query_text, filters_json FROM literature_searches ORDER BY searched_at"):
        if "title_and_abstract.search" in (filters or ""):
            structured.setdefault(text, f"Q{len(structured) + 1}")
            labels[qid] = ("Main search", structured[text])
        else:
            labels[qid] = ("Other sources", f"{db} keyword (top results only)")
    return labels


def sheet_rows(conn: sqlite3.Connection, abstracts: dict[str, str] | None = None) -> list[dict]:
    """All records as sheet rows: Main search first, possible duplicates first within each set."""
    labels = _query_labels(conn)
    rows = [dict(r) for r in conn.execute("SELECT * FROM literature_records")]
    titles = {r["record_id"]: r["title"] for r in rows}
    order = {"Main search": 0, "Other sources": 1}
    rows.sort(key=lambda r: (order[labels.get(r["query_id"], ("Other sources", ""))[0]],
                             r["duplicate_status"] == DEFAULT_DUP, (r["title"] or "").casefold()))
    out = []
    for r in rows:
        source_set, query = labels.get(r["query_id"], ("Other sources", "unknown"))
        dup = r["duplicate_status"]
        out.append({
            "record_id": r["record_id"], "source_set": source_set, "query": query,
            "duplicate_status": dup, "duplicate_of": r["duplicate_of"] or "",
            "duplicate_of_title": titles.get(r["duplicate_of"] or "", ""),
            "dup_decision": dup if dup in DUP_DECISIONS else "",
            "decision": r["screening_status"] if r["screening_status"] in DECISIONS else "",
            "exclusion_reason": r["exclusion_reason"] or "", "note": r["review_note"] or "",
            "title": r["title"], "year": r["year"] or "", "venue": r["venue"] or "",
            "authors": r["authors"] or "", "doi": r["doi"] or "", "record_url": r["record_url"] or "",
            "abstract": (abstracts or {}).get(r["record_id"], ""), "database_name": r["database_name"],
        })
    return out


def export_sheet(conn: sqlite3.Connection, path: Path, abstracts: dict[str, str] | None = None) -> int:
    rows = sheet_rows(conn, abstracts)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return len(rows)


def abstracts_from_csv(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["record_id"]: r.get("abstract") or "" for r in csv.DictReader(f)}


# (column, width, hidden). The decision columns sit next to the record ID so they stay in view.
XLSX_COLUMNS = [
    ("record_id", 21, False), ("decision", 12, False), ("exclusion_reason", 30, False), ("note", 36, False),
    ("dup_decision", 21, False), ("duplicate_status", 17, False), ("duplicate_of_title", 36, False),
    ("title", 48, False), ("abstract", 95, False), ("year", 7, False), ("venue", 28, False),
    ("authors", 28, False), ("doi", 24, False), ("record_url", 30, False),
    ("source_set", 14, True), ("query", 14, True), ("duplicate_of", 21, True), ("database_name", 12, True),
]
WRAPPED = ("title", "abstract", "note", "duplicate_of_title")
INSTRUCTIONS = [
    ("h", "Fill in only the yellow columns on the Screening tab"),
    ("", "decision, exclusion_reason, note and, for flagged rows, dup_decision. Do not edit record_id or "
         "delete rows. Keep the file as .xlsx."),
    ("h", "1. Duplicates (rows whose duplicate_status is not \"No duplicate detected\")"),
    ("", "Compare title with duplicate_of_title. Set dup_decision to \"Confirmed duplicate\" or "
         "\"Distinct record\". Keep the version with the DOI and the fuller metadata."),
    ("h", "2. Title and abstract screening: decision"),
    ("", "Include: research or an official or regulatory source that covers at least one of:"),
    ("", "    C1  Hong Kong's 4S, or smart site safety in Hong Kong;"),
    ("", "    C2  Singapore's VSS, or video surveillance requirements in construction;"),
    ("", "    C3  an evaluation of a construction-safety technology mandate or policy;"),
    ("", "    C4  how well safety-technology coverage aligns with accident or hazard data, or where it falls short;"),
    ("", "    C5  monitoring or sensing of the high-frequency hazards (same-level falls, manual handling or "
         "posture, hand tools) in construction."),
    ("", "Exclude: choose one exclusion_reason from the dropdown:"),
    ("", "    Not construction: a different industry, with no construction findings"),
    ("", "    Not safety or health: productivity or progress monitoring, etc."),
    ("", "    Technology or policy not relevant: construction safety, but no technology or mandate angle"),
    ("", "    No hazard or policy link: purely algorithmic, with no hazard, accident or policy relevance"),
    ("", "    Not research or official source: editorials, news, product notes, abstracts without a paper"),
    ("", "    Not English: no English full text"),
    ("", "    Duplicate: a duplicate missed in step 1"),
    ("", "    (Full text unavailable is for the later full-text stage only.)"),
    ("", "Maybe: the title and abstract cannot decide it. Maybe records go to full-text review."),
    ("h", "3. note"),
    ("", "One line, e.g. \"CV PPE detection on sites, C5\". A red exclusion_reason cell means Exclude with "
         "no reason, or a reason on a row that is not Exclude."),
    ("h", "4. Record the batch (from the project folder)"),
    ("", "python tools/literature_screening_sheet.py import <this file> --reviewer \"Your Name\"           "
         "(dry run: checks only)"),
    ("", "python tools/literature_screening_sheet.py import <this file> --reviewer \"Your Name\" --apply   "
         "(records the decisions)"),
    ("", "You can import a part-done batch: blank rows stay Unscreened, and unchanged rows are skipped."),
]


def _cell(value):
    if isinstance(value, str):
        return ILLEGAL_CHARACTERS_RE.sub("", value)[:32000]
    return value


def _write_workbook(path: Path, rows: list[dict], label: str, columns: list = XLSX_COLUMNS,
                    instructions: list = INSTRUCTIONS, tab: str = SCREEN_TAB) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = tab
    header_fill = PatternFill("solid", fgColor="1F3A5F")
    input_fill = PatternFill("solid", fgColor="FFF2CC")
    grey = PatternFill("solid", fgColor="EDEDED")
    red = PatternFill("solid", fgColor="F4B6B6")
    top, wrap = Alignment(vertical="top"), Alignment(vertical="top", wrap_text=True)
    col = {}
    for i, (name, width, hidden) in enumerate(columns, start=1):
        c = ws.cell(row=1, column=i, value=name)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), header_fill
        col[name] = c.column_letter
        ws.column_dimensions[c.column_letter].width = width
        ws.column_dimensions[c.column_letter].hidden = hidden
    for r, row in enumerate(rows, start=2):
        for i, (name, _, _) in enumerate(columns, start=1):
            value = row[name]
            if name == "year" and str(value).isdigit():
                value = int(value)
            ws.cell(row=r, column=i, value=_cell(value)).alignment = wrap if name in WRAPPED else top
        for name in ("decision", "exclusion_reason", "note"):
            ws[f"{col[name]}{r}"].fill = input_fill
        if "dup_decision" in col:
            ws[f"{col['dup_decision']}{r}"].fill = input_fill if row["duplicate_status"] != DEFAULT_DUP else grey
        if row["record_url"]:
            link = ws[f"{col['record_url']}{r}"]
            link.hyperlink = row["record_url"]
            link.font = Font(color="0563C1", underline="single")
    last = len(rows) + 1
    for name, options in (("decision", DECISIONS), ("exclusion_reason", EXCLUSION_REASONS),
                          ("dup_decision", DUP_DECISIONS)):
        if name not in col:
            continue
        dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True,
                            showErrorMessage=True, errorTitle="Not a listed value",
                            error="Pick a value from the dropdown, or leave the cell blank.")
        dv.add(f"{col[name]}2:{col[name]}{last}")
        ws.add_data_validation(dv)
    d, e = col["decision"], col["exclusion_reason"]
    ws.conditional_formatting.add(f"{e}2:{e}{last}", FormulaRule(
        formula=[f'OR(AND(${d}2="Exclude",${e}2=""),AND(${d}2<>"Exclude",${e}2<>""))'], fill=red))
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{ws.cell(row=1, column=len(columns)).column_letter}{last}"

    info = wb.create_sheet("Instructions")
    info.column_dimensions["A"].width = 120
    info["A1"] = label
    info["A1"].font = Font(bold=True, size=13)
    for n, (kind, line) in enumerate(instructions, start=3):
        c = info.cell(row=n, column=1, value=line)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if kind == "h":
            c.font = Font(bold=True)
    wb.save(path)


def export_xlsx_batches(conn: sqlite3.Connection, out_dir: Path, batch_size: int = 100,
                        abstracts: dict[str, str] | None = None, force: bool = False) -> list[Path]:
    """Write the sheet as numbered workbooks of batch_size records. Refuses to overwrite unless force."""
    if batch_size < 1:
        raise ValueError("--batch-size must be at least 1.")
    rows = sheet_rows(conn, abstracts)
    total = -(-len(rows) // batch_size)
    paths = [out_dir / f"screening_batch_{n:02d}_of_{total:02d}.xlsx" for n in range(1, total + 1)]
    existing = [p for p in paths if p.exists()]
    if existing and not force:
        raise FileExistsError(f"{len(existing)} batch file(s) already exist in {out_dir}, e.g. {existing[0].name}. "
                              "Import them first, or pass --force to overwrite them (decisions already "
                              "imported are kept; anything typed but not imported is lost).")
    out_dir.mkdir(parents=True, exist_ok=True)
    for n, path in enumerate(paths):
        chunk = rows[n * batch_size:(n + 1) * batch_size]
        first = n * batch_size + 1
        sets = " + ".join(dict.fromkeys(r["source_set"] for r in chunk))
        _write_workbook(path, chunk, f"Batch {n + 1} of {total}: records {first}-{first + len(chunk) - 1} "
                                     f"of {len(rows)} ({sets})")
    return paths


def read_sheet(path: Path) -> list[dict]:
    """Rows of a .csv sheet, or of the Screening tab of an .xlsx batch, as {column: text}."""
    if path.suffix.lower() == ".xlsx":
        wb = load_workbook(path, read_only=True, data_only=True)
        try:
            values = wb[SCREEN_TAB].iter_rows(values_only=True)
            header = [str(h or "").strip() for h in next(values)]
            rows = []
            for vals in values:
                if all(v is None or str(v).strip() == "" for v in vals):
                    continue
                rows.append({h: "" if v is None else str(v) for h, v in zip(header, vals) if h})
            return rows
        finally:
            wb.close()
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def import_sheet(conn: sqlite3.Connection, paths: Path | list[Path], reviewer: str,
                 apply: bool) -> dict[str, int]:
    if not reviewer.strip():
        raise ValueError("--reviewer is required.")
    paths = [paths] if isinstance(paths, Path) else list(paths)
    current = {r["record_id"]: dict(r) for r in conn.execute("SELECT * FROM literature_records")}
    errors, changes, seen = [], [], {}
    for path in paths:
        for n, row in enumerate(read_sheet(path), start=2):
            where = f"{path.name} row {n}"
            rid = (row.get("record_id") or "").strip()
            if rid in seen:
                errors.append(f"{where}: record_id {rid} also appears at {seen[rid]}")
                continue
            seen[rid] = where
            saved = current.get(rid)
            if saved is None:
                errors.append(f"{where}: unknown record_id {rid}")
                continue
            decision = (row.get("decision") or "").strip()
            reason = (row.get("exclusion_reason") or "").strip()
            dup = (row.get("dup_decision") or "").strip()
            if decision and decision not in DECISIONS:
                errors.append(f"{where}: decision must be one of {DECISIONS}, not {decision!r}")
            if dup and dup not in DUP_DECISIONS:
                errors.append(f"{where}: dup_decision must be one of {DUP_DECISIONS}, not {dup!r}")
            if decision == "Exclude" and reason not in EXCLUSION_REASONS:
                errors.append(f"{where}: Exclude needs an exclusion_reason from {EXCLUSION_REASONS}")
            if decision != "Exclude" and reason:
                errors.append(f"{where}: exclusion_reason is only for Exclude")
            screening = decision or "Unscreened"
            duplicate = dup or saved["duplicate_status"]
            if (screening, duplicate, reason) == (saved["screening_status"], saved["duplicate_status"],
                                                  saved["exclusion_reason"] or ""):
                continue
            changes.append((rid, screening, duplicate, reason, (row.get("note") or "").strip() or
                            f"Recorded from screening sheet {path.name}"))
    if errors:
        raise ValueError("Sheet has errors; nothing recorded:\n" + "\n".join(errors))
    if apply:
        for rid, screening, duplicate, reason, note in changes:
            review_literature_record(conn, rid, screening, current[rid]["full_text_status"], reviewer, note,
                                     exclusion_reason=reason, duplicate_status=duplicate)
    tally: dict[str, int] = {"changed": len(changes)}
    for _, screening, duplicate, _, _ in changes:
        tally[screening] = tally.get(screening, 0) + 1
        if duplicate in DUP_DECISIONS:
            tally[duplicate] = tally.get(duplicate, 0) + 1
    return tally


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["export", "export-xlsx", "import"])
    parser.add_argument("sheet", type=Path, nargs="+",
                        help="export: CSV file; export-xlsx: output folder; import: one or more .csv/.xlsx files")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--abstracts", action="store_true", help="export, export-xlsx: fetch abstracts from OpenAlex")
    parser.add_argument("--abstracts-from", type=Path, default=None,
                        help=f"export-xlsx: take abstracts from this CSV sheet (default {DEFAULT_CSV.name}, if present)")
    parser.add_argument("--batch-size", type=int, default=100, help="export-xlsx: records per workbook")
    parser.add_argument("--force", action="store_true", help="export-xlsx: overwrite existing batch files")
    parser.add_argument("--reviewer", default="", help="import: name recorded as the screener")
    parser.add_argument("--apply", action="store_true", help="import: write decisions (default is a dry run)")
    args = parser.parse_args()
    if args.command != "import" and len(args.sheet) != 1:
        parser.error(f"{args.command} takes exactly one path")
    conn = connect(args.db)
    try:
        abstracts = None
        if args.command != "import":
            if args.abstracts:
                abstracts = fetch_openalex_abstracts([dict(r) for r in conn.execute(
                    "SELECT record_id, external_id, doi FROM literature_records")])
                print(f"Fetched abstracts for {sum(1 for a in abstracts.values() if a)} records.")
            elif args.command == "export-xlsx":
                source = args.abstracts_from or (DEFAULT_CSV if DEFAULT_CSV.exists() else None)
                if source:
                    abstracts = abstracts_from_csv(source)
                    print(f"Abstracts for {sum(1 for a in abstracts.values() if a)} records from {source.name}.")
        if args.command == "export":
            print(f"Exported {export_sheet(conn, args.sheet[0], abstracts)} records to {args.sheet[0]}")
        elif args.command == "export-xlsx":
            paths = export_xlsx_batches(conn, args.sheet[0], args.batch_size, abstracts, args.force)
            print(f"Wrote {len(paths)} workbooks to {args.sheet[0]}")
        else:
            paths = []  # expand wildcards here, because PowerShell and cmd pass them through unexpanded
            for p in args.sheet:
                matches = sorted(p.parent.glob(p.name)) if any(ch in p.name for ch in "*?[") else [p]
                if not matches:
                    parser.error(f"no files match {p}")
                paths.extend(m for m in matches if not m.name.startswith("~$"))  # skip Excel lock files
            tally = import_sheet(conn, paths, args.reviewer, args.apply)
            print(("Recorded" if args.apply else "Dry run, would record") + f": {tally}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
