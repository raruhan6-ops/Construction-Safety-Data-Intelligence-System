"""Compare two independent coverage codings and report agreement.

Usage (from the project root):

    python tools/compare_coding.py CSDIS_Coverage_Matrix_2025.csv coder_pack/coding_sheet_XY.csv \
        --out coder_pack/disagreements_XY.csv

Reports raw agreement and Cohen's kappa on coverage class (overall and per system), agreement
on Direct scope where both coders chose Direct, a confusion matrix, and writes every row where
the coders differ on class or scope to a CSV for adjudication.
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter

CLASSES = ["Direct", "Indirect", "Uncertain", "No documented coverage"]
SCOPES = {"Full", "Partial", ""}
AUTOMATION = {"Passive recording", "Tracking", "Sensor alert", "AI detection", "Manual review", ""}
CONFIDENCE = {"High", "Medium", "Low"}


def cohen_kappa(a: list[str], b: list[str]) -> float:
    """Cohen's kappa for two raters over the same items (nominal categories)."""
    if len(a) != len(b) or not a:
        raise ValueError("Ratings must be non-empty and of equal length.")
    n = len(a)
    observed = sum(x == y for x, y in zip(a, b)) / n
    count_a, count_b = Counter(a), Counter(b)
    expected = sum(count_a[c] * count_b[c] for c in set(a) | set(b)) / (n * n)
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def load(path: str) -> dict[str, dict[str, str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {row["row_id"]: {k: (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)}


def validate(rows: dict[str, dict[str, str]], label: str) -> list[str]:
    problems = []
    for rid, r in rows.items():
        cls = r.get("coverage_class", "")
        if cls not in CLASSES:
            problems.append(f"{label} {rid}: coverage_class '{cls}' is not one of {CLASSES}")
        scope = r.get("coverage_scope", "")
        if scope not in SCOPES:
            problems.append(f"{label} {rid}: coverage_scope '{scope}' is not Full/Partial/blank")
        if cls == "Direct" and not scope:
            problems.append(f"{label} {rid}: Direct requires coverage_scope")
        if r.get("automation_level", "") not in AUTOMATION:
            problems.append(f"{label} {rid}: automation_level '{r.get('automation_level')}' not allowed")
        if r.get("coder_confidence", "") not in CONFIDENCE:
            problems.append(f"{label} {rid}: coder_confidence '{r.get('coder_confidence')}' not allowed")
        if not r.get("coverage_rationale"):
            problems.append(f"{label} {rid}: rationale is required")
    return problems


def clauses(text: str) -> set[str]:
    return set(re.findall(r"5\(12\)\([a-k]\)", text or ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("coder_a", help="first coding (e.g. the draft matrix)")
    parser.add_argument("coder_b", help="second, independent coding sheet")
    parser.add_argument("--out", help="CSV path for rows needing adjudication")
    args = parser.parse_args(argv)

    a, b = load(args.coder_a), load(args.coder_b)
    if set(a) != set(b):
        print(f"Row IDs differ: only in A {sorted(set(a) - set(b))[:5]}, only in B {sorted(set(b) - set(a))[:5]}")
        return 2
    problems = validate(a, "A") + validate(b, "B")
    if problems:
        print(f"{len(problems)} value problems (fix before comparing):")
        print("\n".join(problems[:40]))
        return 1

    ids = sorted(a)
    print(f"Rows compared: {len(ids)}")
    for system in [None] + sorted({a[i]["system"] for i in ids}):
        subset = [i for i in ids if system is None or a[i]["system"] == system]
        ca = [a[i]["coverage_class"] for i in subset]
        cb = [b[i]["coverage_class"] for i in subset]
        agree = sum(x == y for x, y in zip(ca, cb))
        print(f"  {system or 'All systems'}: class agreement {agree}/{len(subset)} "
              f"({agree / len(subset):.1%}); Cohen's kappa {cohen_kappa(ca, cb):.3f}")

    both_direct = [i for i in ids if a[i]["coverage_class"] == b[i]["coverage_class"] == "Direct"]
    if both_direct:
        same = sum(a[i]["coverage_scope"] == b[i]["coverage_scope"] for i in both_direct)
        print(f"  Scope agreement where both chose Direct: {same}/{len(both_direct)}")
    four_s = [i for i in ids if a[i]["system"] == "HK 4S" and (clauses(a[i]["matched_functions"]) or clauses(b[i]["matched_functions"]))]
    if four_s:
        overlap = sum(bool(clauses(a[i]["matched_functions"]) & clauses(b[i]["matched_functions"])) for i in four_s)
        print(f"  4S rows citing at least one common clause: {overlap}/{len(four_s)}")

    print("\nConfusion matrix (rows = A, columns = B):")
    width = max(len(c) for c in CLASSES) + 2
    print(" " * width + "".join(c[:12].rjust(14) for c in CLASSES))
    for ca_ in CLASSES:
        counts = [sum(1 for i in ids if a[i]["coverage_class"] == ca_ and b[i]["coverage_class"] == cb_) for cb_ in CLASSES]
        print(ca_.ljust(width) + "".join(str(n).rjust(14) for n in counts))

    disagreements = [i for i in ids if (a[i]["coverage_class"], a[i]["coverage_scope"]) != (b[i]["coverage_class"], b[i]["coverage_scope"])]
    print(f"\nRows needing adjudication (class or scope differs): {len(disagreements)}")
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["row_id", "system", "hazard_dimension", "hazard_label_raw", "count_2025",
                        "A_class", "A_scope", "A_functions", "A_rationale", "A_confidence",
                        "B_class", "B_scope", "B_functions", "B_rationale", "B_confidence",
                        "adjudicated_class", "adjudicated_scope", "adjudication_rule_or_reason", "adjudicator", "date"])
            for i in disagreements:
                w.writerow([i, a[i]["system"], a[i]["hazard_dimension"], a[i]["hazard_label_raw"], a[i]["count_2025"],
                            a[i]["coverage_class"], a[i]["coverage_scope"], a[i]["matched_functions"],
                            a[i]["coverage_rationale"], a[i]["coder_confidence"],
                            b[i]["coverage_class"], b[i]["coverage_scope"], b[i]["matched_functions"],
                            b[i]["coverage_rationale"], b[i]["coder_confidence"], "", "", "", "", ""])
        print(f"Written: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
