"""Figure 1: Hong Kong public-works accident rates, 2016-2025, with policy dates (descriptive only).

Reads published values from the local CSDIS database and writes PNG/PDF plus the plotted
data as CSV (the figure's table view). Run from the project root:

    python figures/make_figure1.py
"""
import csv
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "figures"
DB = ROOT / "data" / "local" / "csdis.sqlite3"
YEARS = list(range(2016, 2026))

BLUE, ORANGE = "#2a78d6", "#eb6834"          # categorical slots 1-2 (validated reference palette)
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


def series(conn, source_id, label):
    rows = conn.execute(
        """SELECT m.period_start, m.raw_value FROM metrics m
           JOIN evidence e ON e.evidence_id = m.evidence_id
           JOIN source_versions v ON v.source_version_id = e.source_version_id
           WHERE v.source_id = ? AND m.metric_label_raw = ? AND length(m.period_start) = 4""",
        (source_id, label),
    ).fetchall()
    values = {int(p): float(v) for p, v in rows}
    missing = [y for y in YEARS if y not in values]
    assert not missing, (source_id, label, missing)
    return [values[y] for y in YEARS]


conn = sqlite3.connect(DB)
pw_appendix = series(conn, "S002", "Reportable Accidents rate (b)")    # per 1,000 workers, Appendix A
pw_online = series(conn, "S003", "Accident Rate")                      # per 1,000 workers, DEVB live page
pw_manhours = series(conn, "S002", "Reportable Accidents rate (a)")    # per 100,000 man-hours, Appendix A
industry = series(conn, "S002", "Reportable Accidents rate (c)")       # construction industry, per 1,000 workers
conn.close()

pw_index = [100 * v / pw_appendix[0] for v in pw_appendix]
ind_index = [100 * v / industry[0] for v in industry]

x = [y + 0.5 for y in YEARS]  # annual values plotted at mid-year
POLICY = [(2023 + 1 / 12, "4S required, public works (Feb 2023)"),
          (2024.5, "BD private-works alerts (Jul 2024)"),
          (2025.5, "BD extension (Jul 2025)")]
LABEL_BOX = dict(boxstyle="square,pad=0.15", facecolor=SURFACE, edgecolor="none")

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 8.5, "axes.edgecolor": GRID,
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2})
fig, axes = plt.subplots(3, 1, figsize=(6.6, 8.2), sharex=True, facecolor=SURFACE)


def style(ax, title, ylabel):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.set_title(title, loc="left", fontsize=9.5, color=INK, fontweight="bold")
    ax.set_ylabel(ylabel)
    for xpos, _ in POLICY:
        ax.axvline(xpos, color=INK2, linewidth=0.8, linestyle=(0, (3, 3)), zorder=1)


def line(ax, values, color, dashed=False, open_marker=False, label=None):
    ax.plot(x, values, color=color, linewidth=2, linestyle=(0, (5, 3)) if dashed else "-",
            solid_capstyle="round", zorder=3, label=label)
    ax.scatter(x, values, s=34, zorder=4, linewidths=1.6, edgecolors=color if open_marker else SURFACE,
               facecolors=SURFACE if open_marker else color)


# (a) per 1,000 workers: two published series
ax = axes[0]
style(ax, "(a) Public-works accident rate per 1,000 workers: two published series", "per 1,000 workers")
line(ax, pw_appendix, BLUE, label="DEVB annual appendices (Appendix A)")
line(ax, pw_online, ORANGE, dashed=True, open_marker=True, label="DEVB online historical table")
for i, y in enumerate(YEARS):
    if pw_appendix[i] != pw_online[i]:
        ax.annotate(f"{pw_appendix[i]:.1f} vs {pw_online[i]:.1f}", (x[i], max(pw_appendix[i], pw_online[i])),
                    xytext=(0, 8), textcoords="offset points", ha="center", fontsize=7, color=INK2,
                    bbox=LABEL_BOX, zorder=5)
ax.set_ylim(0, 14)
ax.legend(loc="lower left", frameon=False, fontsize=7.5)
for (xpos, _), tag in zip(POLICY, "ABC"):
    ax.text(xpos, 13.3, tag, ha="center", va="center", fontsize=7.5, fontweight="bold", color=INK2, bbox=LABEL_BOX, zorder=5)

# (b) per 100,000 man-hours: exposure-based, single series
ax = axes[1]
style(ax, "(b) Public-works reportable accident rate per 100,000 man-hours", "per 100,000 man-hours")
line(ax, pw_manhours, BLUE)
ax.annotate(f"{pw_manhours[-1]:.2f}", (x[-1], pw_manhours[-1]), xytext=(6, 0), textcoords="offset points",
            va="center", fontsize=7.5, color=INK)
ax.annotate(f"{pw_manhours[0]:.2f}", (x[0], pw_manhours[0]), xytext=(0, 8), textcoords="offset points",
            va="bottom", ha="center", fontsize=7.5, color=INK)
ax.set_ylim(0, 0.4)

# (c) indexed comparison with the whole construction industry
ax = axes[2]
style(ax, "(c) Public works vs construction industry (accident rate, 2016 = 100)", "index, 2016 = 100")
line(ax, pw_index, BLUE, label="Public works (Appendix A, per 1,000 workers)")
line(ax, ind_index, ORANGE, dashed=True, open_marker=True, label="Construction industry (per 1,000 workers)")
ax.axhline(100, color=INK2, linewidth=0.8, zorder=1)
ax.set_ylim(0, 130)
ax.legend(loc="lower left", frameon=False, fontsize=7.5)
for vals in (pw_index, ind_index):
    ax.annotate(f"{vals[-1]:.0f}", (x[-1], vals[-1]), xytext=(6, 0), textcoords="offset points",
                va="center", fontsize=7.5, color=INK)

axes[-1].set_xticks(x, [str(y) for y in YEARS])
axes[-1].set_xlim(2016, 2026.4)
fig.text(0.01, 0.005,
         "Sources: DEVB All Appendices 2025, Appendix A; DEVB Overall Accident Rates webpage (accessed 17 Nov 2026). "
         "Annual values at mid-year.\nPolicy dates (dashed): A = 4S required for public works (Feb 2023); "
         "B = Buildings Department private-works alerts (Jul 2024);\n"
         "C = Buildings Department extension to further work types (Jul 2025).\n"
         "Descriptive only: the mandate covers eligible contracts, and industry figures include public works.",
         fontsize=6.5, color=INK2, va="bottom")
fig.tight_layout(rect=(0, 0.075, 1, 1))
for ext in ("png", "pdf"):
    fig.savefig(OUT / f"Figure1_HK_accident_rates_2016_2025.{ext}", dpi=300, facecolor=SURFACE)

with open(OUT / "Figure1_data.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["year", "public_works_per_1000_workers_appendixA", "public_works_per_1000_workers_online",
                "public_works_per_100000_manhours_appendixA", "construction_industry_per_1000_workers_appendixA",
                "public_works_index_2016_100", "industry_index_2016_100"])
    for i, y in enumerate(YEARS):
        w.writerow([y, pw_appendix[i], pw_online[i], pw_manhours[i], industry[i], round(pw_index[i], 1), round(ind_index[i], 1)])
print("written to", OUT)
