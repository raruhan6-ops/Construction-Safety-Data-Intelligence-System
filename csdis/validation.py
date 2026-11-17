"""Denominator-aware arithmetic validation for reviewed metric records."""

from __future__ import annotations

import sqlite3
import uuid

from csdis.database import audit, now_iso


def _normalized_label(value: str) -> str:
    """Normalize spacing/case only; do not merge labels by loose similarity."""
    return " ".join((value or "").casefold().split())


def detect_metric_conflicts(connection: sqlite3.Connection, metric_id: str) -> list[str]:
    """Create unresolved conflicts for comparable records with different values.

    Exact label, cohort, period, jurisdiction, classification and unit are used
    as the candidate key. No record is selected or overwritten.
    """
    current = connection.execute(
        """SELECT m.*, e.source_version_id, e.page_or_section FROM metrics m
           JOIN evidence e ON e.evidence_id=m.evidence_id WHERE m.metric_id=?""",
        (metric_id,),
    ).fetchone()
    if current is None:
        return []
    candidates = connection.execute(
        """SELECT m.*, e.source_version_id, e.page_or_section FROM metrics m
           JOIN evidence e ON e.evidence_id=m.evidence_id
           WHERE m.metric_id != ? AND m.jurisdiction=? AND m.sector_or_cohort=?
             AND m.period_start=? AND m.period_end=? AND m.classification_dimension=? AND m.unit=?""",
        (metric_id, current["jurisdiction"], current["sector_or_cohort"], current["period_start"],
         current["period_end"], current["classification_dimension"], current["unit"]),
    ).fetchall()
    created: list[str] = []
    for prior in candidates:
        prior_label = prior["metric_label_harmonised"] or prior["metric_label_raw"]
        current_label = current["metric_label_harmonised"] or current["metric_label_raw"]
        if _normalized_label(prior_label) != _normalized_label(current_label):
            continue
        if prior["numeric_value"] is not None and current["numeric_value"] is not None:
            same_value = float(prior["numeric_value"]) == float(current["numeric_value"])
        else:
            same_value = prior["raw_value"].strip() == current["raw_value"].strip()
        if same_value:
            continue
        existing = connection.execute(
            """SELECT 1 FROM conflicts WHERE
               (metric_a_id=? AND metric_b_id=?) OR (metric_a_id=? AND metric_b_id=?)""",
            (prior["metric_id"], metric_id, metric_id, prior["metric_id"]),
        ).fetchone()
        if existing:
            continue
        same_denominator = (prior["denominator_definition"] or "").strip().casefold() == (
            current["denominator_definition"] or ""
        ).strip().casefold()
        severity = "High" if same_denominator else "Medium"
        conflict_id = "conflict-" + uuid.uuid4().hex[:16]
        description = (
            f"Comparable metric key has differing values: {prior['raw_value']} vs {current['raw_value']}. "
            f"Denominator definitions: {prior['denominator_definition'] or '[missing]'} vs "
            f"{current['denominator_definition'] or '[missing]'}. Source versions and definitions require human review."
        )
        connection.execute(
            """INSERT INTO conflicts (conflict_id, metric_a_id, metric_b_id, severity, status,
               description, created_at) VALUES (?, ?, ?, ?, 'Open', ?, ?)""",
            (conflict_id, prior["metric_id"], metric_id, severity, description, now_iso()),
        )
        audit(connection, "metric_conflict_detected", "conflict", conflict_id,
              {"metric_a_id": prior["metric_id"], "metric_b_id": metric_id, "severity": severity,
               "source_versions": [prior["source_version_id"], current["source_version_id"]]})
        created.append(conflict_id)
    return created


def metric_issues(connection: sqlite3.Connection) -> list[dict[str, str]]:
    """Return non-destructive validation findings for metric rows."""
    findings: list[dict[str, str]] = []
    rows = connection.execute("SELECT * FROM metrics ORDER BY metric_id").fetchall()
    percentage_groups: dict[tuple[object, ...], list[sqlite3.Row]] = {}
    for row in rows:
        metric_id = row["metric_id"]
        unit = (row["unit"] or "").strip().lower()
        denominator = row["denominator"]
        numerator = row["numerator"]
        label = row["metric_label_raw"]
        if not unit:
            findings.append({"metric_id": metric_id, "severity": "Error", "issue": "Missing unit."})
        if not row["denominator_definition"]:
            findings.append({"metric_id": metric_id, "severity": "Error", "issue": "Missing denominator meaning."})
        if ("%" in unit or "percent" in unit or "percentage" in unit) and row["numeric_value"] is not None:
            if denominator is None or denominator == 0 or numerator is None:
                findings.append({"metric_id": metric_id, "severity": "Error", "issue": "Percentage requires a non-zero denominator and stored numerator."})
            else:
                expected = 100 * numerator / denominator
                if abs(expected - row["numeric_value"]) > 0.1:
                    findings.append({
                        "metric_id": metric_id,
                        "severity": "Error",
                        "issue": f"Published percentage {row['numeric_value']:g}% does not match {numerator:g}/{denominator:g} = {expected:.4f}% within 0.1 percentage point.",
                    })
            if denominator is not None and denominator != 0:
                group_key = (
                    row["jurisdiction"], row["sector_or_cohort"], row["period_start"],
                    row["period_end"], row["classification_dimension"], float(denominator),
                    (row["denominator_definition"] or "").strip().casefold(), unit,
                )
                percentage_groups.setdefault(group_key, []).append(row)
        if denominator is None and ("%" in unit or "rate" in label.lower()):
            findings.append({"metric_id": metric_id, "severity": "Warning", "issue": "Ratio or rate has no explicit denominator value."})
    for group_rows in percentage_groups.values():
        if len(group_rows) < 2:
            continue
        total = sum(float(row["numeric_value"]) for row in group_rows)
        if total > 100.1:
            findings.append({
                "metric_id": ", ".join(row["metric_id"] for row in group_rows),
                "severity": "Warning",
                "issue": (f"Grouped percentages sum to {total:.2f}% (>100%). Confirm whether this taxonomy permits "
                          "multiple responses or whether the records use different bases."),
            })
    return findings
