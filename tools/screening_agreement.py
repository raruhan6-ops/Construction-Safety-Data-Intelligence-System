"""Second-screener sample and screening agreement for the literature register.

Usage (from the project root):

    python tools/screening_agreement.py sample data/local/second_screener_sample.xlsx [--fraction 0.2] [--seed 20261121]
    python tools/screening_agreement.py compare data/local/second_screener_sample.xlsx

sample draws a fixed-seed random sample of the register and writes it as a workbook for the second
screener. It holds no decisions, lists records in random order, and uses its own tab name, so the
import in literature_screening_sheet.py cannot read it. A manifest CSV (record IDs and seed) is
written next to it.

compare reads the returned workbook and compares it with the decisions recorded in CSDIS (the
primary screener's). It excludes records the primary removed as confirmed duplicates and records
either screener left blank, then reports percentage agreement and Cohen's kappa on the three-way
decision (Include/Exclude/Maybe) and on the binary decision (Exclude vs Include or Maybe), and
writes the disagreements to a CSV for joint resolution. Nothing is written to the database.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import random
import sys
from collections import Counter
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from csdis.database import connect

_spec = importlib.util.spec_from_file_location("screening_sheet", ROOT / "tools" / "literature_screening_sheet.py")
sheet = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sheet)

TAB = "Second screener"
DEFAULT_SEED = 20261121
COLUMNS = [
    ("record_id", 21, False), ("decision", 12, False), ("exclusion_reason", 30, False), ("note", 36, False),
    ("title", 50, False), ("abstract", 95, False), ("year", 7, False), ("venue", 28, False),
    ("authors", 28, False), ("doi", 24, False), ("record_url", 30, False),
]
INSTRUCTIONS = [
    ("h", "You are the second screener for a random sample of the literature register"),
    ("", "Screen each record on its own from the title and abstract. Don't discuss individual records with the "
         "primary screener until you have both finished. Fill in only the yellow columns: decision, "
         "exclusion_reason and note. Do not edit record_id or delete rows. Keep the file as .xlsx."),
    ("h", "decision"),
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
    ("", "    Duplicate: the same work appears twice in this sample"),
    ("", "    (Full text unavailable is for the later full-text stage only; don't use it here.)"),
    ("", "Maybe: the title and abstract cannot decide it."),
    ("h", "note"),
    ("", "One line, e.g. \"CV PPE detection on sites, C5\". A red exclusion_reason cell means Exclude with no "
         "reason, or a reason on a row that is not Exclude."),
    ("h", "When you have finished"),
    ("", "Send the file back to the primary screener. Do NOT run literature_screening_sheet.py import on it: "
         "that would write your decisions over the primary screener's. The file is compared separately with "
         "tools/screening_agreement.py."),
]


def cohen_kappa(a: list[str], b: list[str]) -> float:
    """Cohen's kappa for two raters over the same items (nominal categories)."""
    if len(a) != len(b) or not a:
        raise ValueError("Ratings must be non-empty and of equal length.")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[c] * count_b[c] for c in set(a) | set(b)) / (n * n)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def write_sample(conn, out: Path, fraction: float, seed: int, abstracts: dict[str, str] | None) -> list[str]:
    if out.exists():
        raise FileExistsError(f"{out} already exists; it may hold returned decisions. Choose another path.")
    if not 0 < fraction <= 1:
        raise ValueError("--fraction must be in (0, 1].")
    rows = sorted(sheet.sheet_rows(conn, abstracts), key=lambda r: r["record_id"])
    k = round(fraction * len(rows))
    chosen = random.Random(seed).sample(rows, k)  # random order too, so no grouping by query or duplicate flag
    for r in chosen:
        r["decision"] = r["exclusion_reason"] = r["note"] = ""
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet._write_workbook(out, chosen, f"Second-screener sample: {k} of {len(rows)} records "
                                       f"({fraction:.0%}, seed {seed})", COLUMNS, INSTRUCTIONS, TAB)
    manifest = out.with_name(out.stem + "_manifest.csv")
    with manifest.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["order", "record_id", "seed", "fraction", "register_size"])
        for i, r in enumerate(chosen, start=1):
            w.writerow([i, r["record_id"], seed, fraction, len(rows)])
    return [r["record_id"] for r in chosen]


def read_second(path: Path) -> dict[str, dict[str, str]]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        values = wb[TAB].iter_rows(values_only=True)
        header = [str(h or "").strip() for h in next(values)]
        out = {}
        for vals in values:
            row = {h: "" if v is None else str(v).strip() for h, v in zip(header, vals) if h}
            if row.get("record_id"):
                out[row["record_id"]] = row
        return out
    finally:
        wb.close()


def compare(conn, path: Path) -> dict:
    second = read_second(path)
    errors = []
    for rid, r in second.items():
        if r["decision"] and r["decision"] not in sheet.DECISIONS:
            errors.append(f"{rid}: decision {r['decision']!r} is not one of {sheet.DECISIONS}")
        if r["decision"] == "Exclude" and r["exclusion_reason"] not in sheet.EXCLUSION_REASONS:
            errors.append(f"{rid}: Exclude needs an exclusion_reason")
    if errors:
        raise ValueError("Second screener's file has errors:\n" + "\n".join(errors))
    primary = {r["record_id"]: dict(r) for r in conn.execute(
        "SELECT record_id, title, screening_status, exclusion_reason, duplicate_status FROM literature_records")}
    missing = sorted(set(second) - set(primary))
    if missing:
        raise ValueError(f"{len(missing)} record IDs are not in the register, e.g. {missing[0]}")
    counts = Counter()
    pairs = []
    for rid, r in second.items():
        p = primary[rid]
        if p["duplicate_status"] == "Confirmed duplicate":
            counts["removed as duplicate by primary"] += 1
        elif not r["decision"]:
            counts["blank in second file"] += 1
        elif p["screening_status"] not in sheet.DECISIONS:
            counts["not yet screened by primary"] += 1
        else:
            pairs.append((rid, p, r))
    report = {"sample": len(second), "compared": len(pairs), "skipped": dict(counts)}
    if not pairs:
        return report | {"disagreements": []}
    a = [p["screening_status"] for _, p, _ in pairs]
    b = [r["decision"] for _, _, r in pairs]
    binary = lambda xs: ["Exclude" if x == "Exclude" else "Include or Maybe" for x in xs]
    report |= {
        "three_way": {"agree": sum(x == y for x, y in zip(a, b)), "kappa": round(cohen_kappa(a, b), 3)},
        "binary": {"agree": sum(x == y for x, y in zip(binary(a), binary(b))),
                   "kappa": round(cohen_kappa(binary(a), binary(b)), 3)},
        "confusion (primary -> second)": dict(Counter(f"{x} -> {y}" for x, y in zip(a, b))),
        "disagreements": [(rid, p["title"], p["screening_status"], p["exclusion_reason"] or "",
                           r["decision"], r["exclusion_reason"], r.get("note", ""))
                          for rid, p, r in pairs if p["screening_status"] != r["decision"]],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["sample", "compare"])
    parser.add_argument("file", type=Path)
    parser.add_argument("--db", type=Path, default=sheet.DEFAULT_DB)
    parser.add_argument("--fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--abstracts-from", type=Path, default=None,
                        help=f"sample: CSV sheet with abstracts (default {sheet.DEFAULT_CSV.name}, if present)")
    args = parser.parse_args()
    conn = connect(args.db)
    try:
        if args.command == "sample":
            source = args.abstracts_from or (sheet.DEFAULT_CSV if sheet.DEFAULT_CSV.exists() else None)
            abstracts = sheet.abstracts_from_csv(source) if source else None
            ids = write_sample(conn, args.file, args.fraction, args.seed, abstracts)
            print(f"Wrote {len(ids)} records to {args.file} (seed {args.seed}); manifest next to it.")
        else:
            report = compare(conn, args.file)
            dis = report.pop("disagreements")
            for k, v in report.items():
                print(f"{k}: {v}")
            n = report["compared"]
            if n:
                for key in ("three_way", "binary"):
                    r = report[key]
                    print(f"{key}: {r['agree']}/{n} agree ({r['agree'] / n:.1%}), kappa = {r['kappa']}")
            out = args.file.with_name(args.file.stem + "_disagreements.csv")
            with out.open("w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["record_id", "title", "primary_decision", "primary_reason",
                            "second_decision", "second_reason", "second_note"])
                w.writerows(dis)
            print(f"{len(dis)} disagreements written to {out}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
