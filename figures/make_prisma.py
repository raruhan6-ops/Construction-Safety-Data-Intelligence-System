"""Figure S1: PRISMA 2020 flow diagram of the literature search and selection.

Counts are computed, not typed: identification and title/abstract screening come from the frozen
screening decisions (data/local/title_abstract_decisions_FROZEN.csv); full-text retrieval and
eligibility come from the local CSDIS database. The script checks that every box adds up, then
writes PNG/PDF plus the counts as CSV. Run from the project root:

    python figures/make_prisma.py
"""
import csv
import re
import sqlite3
import textwrap
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, Rectangle  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures"
DB = ROOT / "data" / "local" / "csdis.sqlite3"
FROZEN = ROOT / "data" / "local" / "title_abstract_decisions_FROZEN.csv"

INK, INK2, LINE, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#fcfcfb"
STAGE, BOX = "#2a78d6", "#ffffff"
UNAVAILABLE = "Full text unavailable"

# --- counts -------------------------------------------------------------------------------
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
source_set = {}
for qid, filters in conn.execute("SELECT query_id, filters_json FROM literature_searches"):
    source_set[qid] = "main" if "title_and_abstract.search" in (filters or "") else "other"
now = {r["record_id"]: r for r in conn.execute("SELECT * FROM literature_records")}
conn.close()
with FROZEN.open(encoding="utf-8-sig", newline="") as f:
    frozen = {r["record_id"]: r for r in csv.DictReader(f)}

origin = Counter(source_set.get(now[rid]["query_id"], "other") for rid in frozen)
duplicates = [rid for rid, r in frozen.items() if r["exclusion_reason"] == "Duplicate"]
dup_flagged = sum(frozen[rid]["duplicate_status"] == "Confirmed duplicate" for rid in duplicates)
screened = [rid for rid in frozen if rid not in duplicates]
ta_excluded = [rid for rid in screened if frozen[rid]["screening_status"] == "Exclude"]
sought = [rid for rid in screened if frozen[rid]["screening_status"] in ("Include", "Maybe")]
not_retrieved = [rid for rid in sought if now[rid]["full_text_status"] == "Unavailable"]
assessed = [rid for rid in sought if rid not in not_retrieved]
ft_excluded = [rid for rid in assessed if now[rid]["screening_status"] == "Exclude"]
included = [rid for rid in assessed if now[rid]["screening_status"] == "Include"]

assert len(frozen) == origin["main"] + origin["other"]
assert len(screened) == len(ta_excluded) + len(sought), "unscreened records remain"
assert any(now[rid]["full_text_status"] == "Metadata only" for rid in sought) is False, "full-text review unfinished"
assert len(assessed) == len(ft_excluded) + len(included), "undecided full-text records remain"
assert all(now[rid]["exclusion_reason"] == UNAVAILABLE for rid in not_retrieved)

ta_reasons = Counter(frozen[rid]["exclusion_reason"] for rid in ta_excluded).most_common()
ft_reasons = Counter(now[rid]["exclusion_reason"] for rid in ft_excluded).most_common()
inc_origin = Counter(source_set.get(now[rid]["query_id"], "other") for rid in included)


def n(x):
    return f"{len(x) if not isinstance(x, int) else x:,}"


def lower_first(s):
    return s[0].lower() + s[1:]


# --- drawing ------------------------------------------------------------------------------
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8})
fig = plt.figure(figsize=(7.4, 9.4), facecolor=SURFACE)
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100)
ax.set_ylim(0, 125)
ax.axis("off")

LX, LW = 9, 44          # left (flow) column
RX, RW = 59, 39         # right (removed/excluded) column


def box(x, y_top, w, lines, bold_first=True):
    """Draw a text box whose top edge is at y_top; return (top, bottom, centre_y)."""
    wrapped = []
    for i, line in enumerate(lines):
        indent = "    " if line.startswith("  ") else ""
        bold = i == 0 and bold_first
        width = int(w * (1.04 if bold else 1.2)) - len(indent)
        # Non-breaking spaces keep each "(n = 123)" on one line.
        text = re.sub(r"\(n = ([\d,]+)\)", "(n = \\1)", line.strip())
        for j, part in enumerate(textwrap.wrap(text, width=width)):
            wrapped.append(((indent if j == 0 else indent + "  ") + part, bold))
    h = 2.2 * len(wrapped) + 2.4
    ax.add_patch(Rectangle((x, y_top - h), w, h, facecolor=BOX, edgecolor=LINE, linewidth=0.9))
    for k, (text, bold) in enumerate(wrapped):
        ax.text(x + 1.4, y_top - 1.9 - 2.2 * k, text, ha="left", va="center", color=INK,
                fontweight="bold" if bold else "normal")
    return y_top, y_top - h, y_top - h / 2


def arrow(x1, y1, x2, y2):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=9,
                                 color=INK2, linewidth=0.9, shrinkA=0, shrinkB=0))


def stage(label, top, bottom):
    ax.add_patch(Rectangle((1.5, bottom), 5, top - bottom, facecolor=STAGE, edgecolor="none"))
    ax.text(4, (top + bottom) / 2, label, rotation=90, ha="center", va="center", color="white",
            fontweight="bold", fontsize=7)


ax.text(50, 122.5, "Identification of studies via databases and other sources", ha="center",
        va="center", fontsize=10, fontweight="bold", color=INK)

GAP = 4.5
# Identification
t1, b1, c1 = box(LX, 118, LW, [f"Records identified (n = {n(len(frozen))})",
                                f"  OpenAlex structured title/abstract search (n = {n(origin['main'])})",
                                f"  Other sources: exploratory OpenAlex and Crossref keyword searches, "
                                f"top results only (n = {n(origin['other'])})"])
tr1, br1, cr1 = box(RX, 118, RW, [f"Records removed before screening (n = {n(duplicates)})",
                                  f"  Duplicate records matched by DOI or normalized title (n = {n(dup_flagged)})",
                                  f"  Duplicates found during screening (n = {n(len(duplicates) - dup_flagged)})"])
arrow(LX + LW, c1, RX, c1)
stage("Identification", 118, min(b1, br1))

# Screening: title/abstract
y = min(b1, br1) - GAP
t2, b2, c2 = box(LX, y, LW, [f"Records screened on title and abstract (n = {n(screened)})"])
tr2, br2, cr2 = box(RX, y, RW, [f"Records excluded (n = {n(ta_excluded)})"]
                    + [f"  {r} (n = {c:,})" for r, c in ta_reasons])
arrow(LX + LW / 2, b1, LX + LW / 2, t2)
arrow(LX + LW, c2, RX, c2)

# Retrieval
y = min(b2, br2) - GAP
t3, b3, c3 = box(LX, y, LW, [f"Reports sought for retrieval (n = {n(sought)})"])
tr3, br3, cr3 = box(RX, y, RW, [f"Reports not retrieved (n = {n(not_retrieved)})"])
arrow(LX + LW / 2, b2, LX + LW / 2, t3)
arrow(LX + LW, c3, RX, c3)

# Eligibility
y = min(b3, br3) - GAP
t4, b4, c4 = box(LX, y, LW, [f"Reports assessed for eligibility (full text) (n = {n(assessed)})"])
reason_text = {"Duplicate": "Duplicate report of an included study",
               "Not research or official source": "Not research or official source (conference abstract only)"}
tr4, br4, cr4 = box(RX, y, RW, [f"Reports excluded (n = {n(ft_excluded)})"]
                    + [f"  {reason_text.get(r, r)} (n = {c:,})" for r, c in ft_reasons])
arrow(LX + LW / 2, b3, LX + LW / 2, t4)
arrow(LX + LW, c4, RX, c4)
stage("Screening", min(b1, br1) - GAP, min(b4, br4))

# Included
y = min(b4, br4) - GAP
t5, b5, c5 = box(LX, y, LW, [f"Studies included in review (n = {n(included)})",
                              f"  From the database search (n = {inc_origin['main']:,})",
                              f"  From other sources (n = {inc_origin['other']:,})"])
arrow(LX + LW / 2, b4, LX + LW / 2, t5)
stage("Included", y, b5)

ax.text(1.5, b5 - 3.5, "Flow follows the PRISMA 2020 statement (Page et al., 2021). Record counts are computed "
        "from the CSDIS screening register.", ha="left", va="center", fontsize=6.5, color=INK2)

# Crop the empty space below the content, keeping the vertical scale unchanged.
bottom = b5 - 6.5
ax.set_ylim(bottom, 125)
fig.set_size_inches(7.4, 9.4 * (125 - bottom) / 125)

for ext in ("png", "pdf"):
    fig.savefig(OUT / f"FigureS1_PRISMA_2020.{ext}", dpi=300, facecolor=SURFACE)

rows = [("records_identified", len(frozen)), ("identified_database_search", origin["main"]),
        ("identified_other_sources", origin["other"]), ("duplicates_removed", len(duplicates)),
        ("duplicates_matched_by_doi_or_title", dup_flagged),
        ("duplicates_found_during_screening", len(duplicates) - dup_flagged),
        ("records_screened", len(screened)), ("records_excluded_title_abstract", len(ta_excluded))]
rows += [(f"title_abstract_excluded: {r}", c) for r, c in ta_reasons]
rows += [("reports_sought", len(sought)), ("reports_not_retrieved", len(not_retrieved)),
         ("reports_assessed", len(assessed)), ("reports_excluded_full_text", len(ft_excluded))]
rows += [(f"full_text_excluded: {r}", c) for r, c in ft_reasons]
rows += [("studies_included", len(included)), ("included_from_database_search", inc_origin["main"]),
         ("included_from_other_sources", inc_origin["other"])]
with open(OUT / "FigureS1_data.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["count", "n"])
    w.writerows(rows)
print("\n".join(f"{k}: {v}" for k, v in rows))
