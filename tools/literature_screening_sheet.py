"""Screen the literature register in a spreadsheet, then record the decisions in CSDIS.

Usage (from the project root):

    python tools/literature_screening_sheet.py export screening_sheet.csv [--abstracts]
    python tools/literature_screening_sheet.py import screening_sheet.csv --reviewer "Name"          # dry run
    python tools/literature_screening_sheet.py import screening_sheet.csv --reviewer "Name" --apply  # write

Fill in these columns of the exported sheet and leave everything else alone:

- dup_decision: Confirmed duplicate or Distinct record (only for rows flagged as possible duplicates);
- decision: Include, Exclude or Maybe;
- exclusion_reason: one of EXCLUSION_REASONS, required for Exclude;
- note: optional; when blank, the note records that the decision came from the sheet.

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from csdis.database import connect
from csdis.literature import review_literature_record

DEFAULT_DB = ROOT / "data" / "local" / "csdis.sqlite3"
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


def export_sheet(conn: sqlite3.Connection, path: Path, abstracts: dict[str, str] | None = None) -> int:
    labels = _query_labels(conn)
    rows = [dict(r) for r in conn.execute("SELECT * FROM literature_records")]
    titles = {r["record_id"]: r["title"] for r in rows}
    order = {"Main search": 0, "Other sources": 1}
    rows.sort(key=lambda r: (order[labels.get(r["query_id"], ("Other sources", ""))[0]],
                             r["duplicate_status"] == DEFAULT_DUP, (r["title"] or "").casefold()))
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            source_set, query = labels.get(r["query_id"], ("Other sources", "unknown"))
            dup = r["duplicate_status"]
            w.writerow({
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
    return len(rows)


def import_sheet(conn: sqlite3.Connection, path: Path, reviewer: str, apply: bool) -> dict[str, int]:
    if not reviewer.strip():
        raise ValueError("--reviewer is required.")
    with path.open(encoding="utf-8-sig", newline="") as f:
        sheet = list(csv.DictReader(f))
    current = {r["record_id"]: dict(r) for r in conn.execute("SELECT * FROM literature_records")}
    errors, changes = [], []
    for n, row in enumerate(sheet, start=2):
        rid = row["record_id"]
        saved = current.get(rid)
        if saved is None:
            errors.append(f"line {n}: unknown record_id {rid}")
            continue
        decision = row["decision"].strip()
        reason = row["exclusion_reason"].strip()
        dup = row["dup_decision"].strip()
        if decision and decision not in DECISIONS:
            errors.append(f"line {n}: decision must be one of {DECISIONS}, not {decision!r}")
        if dup and dup not in DUP_DECISIONS:
            errors.append(f"line {n}: dup_decision must be one of {DUP_DECISIONS}, not {dup!r}")
        if decision == "Exclude" and reason not in EXCLUSION_REASONS:
            errors.append(f"line {n}: Exclude needs an exclusion_reason from {EXCLUSION_REASONS}")
        if decision != "Exclude" and reason:
            errors.append(f"line {n}: exclusion_reason is only for Exclude")
        screening = decision or "Unscreened"
        duplicate = dup or saved["duplicate_status"]
        if (screening, duplicate, reason) == (saved["screening_status"], saved["duplicate_status"],
                                              saved["exclusion_reason"] or ""):
            continue
        changes.append((rid, screening, duplicate, reason, row["note"].strip() or
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
    parser.add_argument("command", choices=["export", "import"])
    parser.add_argument("sheet", type=Path)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--abstracts", action="store_true", help="export: fetch abstracts from OpenAlex")
    parser.add_argument("--reviewer", default="", help="import: name recorded as the screener")
    parser.add_argument("--apply", action="store_true", help="import: write decisions (default is a dry run)")
    args = parser.parse_args()
    conn = connect(args.db)
    try:
        if args.command == "export":
            abstracts = None
            if args.abstracts:
                abstracts = fetch_openalex_abstracts([dict(r) for r in conn.execute(
                    "SELECT record_id, external_id, doi FROM literature_records")])
                print(f"Fetched abstracts for {sum(1 for a in abstracts.values() if a)} records.")
            print(f"Exported {export_sheet(conn, args.sheet, abstracts)} records to {args.sheet}")
        else:
            tally = import_sheet(conn, args.sheet, args.reviewer, args.apply)
            print(("Recorded" if args.apply else "Dry run, would record") + f": {tally}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
