"""Local regression tests for DEVB live rate extraction and conflict detection."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from csdis.database import connect
from csdis.ingestion import extract_devb_live_rates, extract_html_tables
from csdis.validation import detect_metric_conflicts, metric_issues


@pytest.fixture
def db(tmp_path: Path):
    connection = connect(tmp_path / "csdis.sqlite3")
    now = "2026-01-01T00:00:00+00:00"
    connection.execute(
        """INSERT INTO sources (source_id, publisher, title, source_type, canonical_url,
           format, authority_tier, created_at, updated_at)
           VALUES ('S-TEST', 'DEVB', 'Test rates', 'Statistics', 'https://example.invalid',
           'HTML', 'Official', ?, ?)""", (now, now)
    )
    source_version_id = "S-TEST-v1"
    connection.execute(
        """INSERT INTO source_versions (source_version_id, source_id, version_label,
           original_filename, storage_path, sha256, file_size, content_type, retrieved_at,
           retrieval_method) VALUES (?, 'S-TEST', 'fixture', 'rates.html', 'rates.html',
           ?, 0, 'text/html', ?, 'test fixture')""",
        (source_version_id, hashlib.sha256(b"fixture").hexdigest(), now),
    )
    connection.commit()
    yield connection, source_version_id
    connection.close()


def _metric(connection, evidence_id: str, metric_id: str, period: str, raw_value: str) -> None:
    connection.execute(
        """INSERT INTO metrics (metric_id, evidence_id, jurisdiction, sector_or_cohort,
           period_start, period_end, metric_label_raw, metric_label_harmonised,
           classification_dimension, denominator_definition, raw_value, numeric_value,
           unit, verification_status)
           VALUES (?, ?, 'Hong Kong', 'Public works contracts', ?, ?, 'Annual rate',
           'reportable annual accident rate', 'Rate', 'per 1,000 workers per year', ?, ?,
           'accidents per 1,000 workers per year', 'Unverified')""",
        (metric_id, evidence_id, period, period, raw_value, float(raw_value)),
    )


def test_extracts_monthly_rolling_values_as_distinct_periods_and_is_idempotent(db, tmp_path: Path):
    connection, source_version_id = db
    html = tmp_path / "rates.html"
    html.write_text(
        """<table>
          <tr><th>2026</th></tr>
          <tr><th>Month</th><th>JAN</th><th>FEB</th><th>MAR</th></tr>
          <tr><td>Monthly Average</td><td>3.1</td><td>3.1</td><td></td></tr>
          <tr><td>Rolling 12 Month Average</td><td>4.9</td><td>4.8</td><td></td></tr>
        </table>
        <table>
          <tr><th>Year</th><th>2025</th></tr>
          <tr><td>Accident Rate</td><td>4.6</td></tr>
        </table>""",
        encoding="utf-8",
    )

    assert extract_html_tables(html, source_version_id, connection) == 6
    assert extract_devb_live_rates(html, source_version_id, connection) == 3

    rows = connection.execute(
        """SELECT period_start, metric_label_harmonised, raw_value, numeric_value
           FROM metrics ORDER BY period_start"""
    ).fetchall()
    assert [(row["period_start"], row["raw_value"]) for row in rows] == [
        ("2025", "4.6"), ("2026-01", "4.9"), ("2026-02", "4.8")
    ]
    assert rows[1]["metric_label_harmonised"] == "Monthly rolling 12-month accident rate"
    assert rows[2]["numeric_value"] == pytest.approx(4.8)
    assert connection.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0] == 0

    assert extract_devb_live_rates(html, source_version_id, connection) == 0
    assert connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0] == 3


def test_conflict_detection_requires_same_period_and_definition(db):
    connection, source_version_id = db
    for evidence_id, row_id in (("ev-a", "row-a"), ("ev-b", "row-b"), ("ev-c", "row-c")):
        connection.execute(
            """INSERT INTO evidence (evidence_id, source_version_id, page_or_section,
               exact_quote_or_excerpt, locator_type, extraction_method, review_status,
               confidence, created_at) VALUES (?, ?, ?, 'rate', 'table row', 'fixture',
               'Unreviewed', 'high', '2026-01-01T00:00:00+00:00')""",
            (evidence_id, source_version_id, row_id),
        )
    _metric(connection, "ev-a", "metric-a", "2025", "4.6")
    _metric(connection, "ev-b", "metric-b", "2025", "4.8")
    _metric(connection, "ev-c", "metric-c", "2026-02", "4.8")

    created = detect_metric_conflicts(connection, "metric-b")
    assert len(created) == 1
    conflict = connection.execute(
        "SELECT * FROM conflicts WHERE conflict_id=?", (created[0],)
    ).fetchone()
    assert conflict["status"] == "Open"
    assert conflict["severity"] == "High"
    assert detect_metric_conflicts(connection, "metric-b") == []
    assert detect_metric_conflicts(connection, "metric-c") == []
    assert connection.execute("SELECT COUNT(*) FROM conflicts").fetchone()[0] == 1


def test_percentage_validation_flags_missing_denominator_but_accepts_matching_ratio(db):
    connection, source_version_id = db
    for evidence_id in ("ev-missing", "ev-valid"):
        connection.execute(
            """INSERT INTO evidence (evidence_id, source_version_id, page_or_section,
               exact_quote_or_excerpt, locator_type, extraction_method, review_status,
               confidence, created_at) VALUES (?, ?, ?, 'percentage', 'table row', 'fixture',
               'Unreviewed', 'high', '2026-01-01T00:00:00+00:00')""",
            (evidence_id, source_version_id, evidence_id),
        )
    connection.execute(
        """INSERT INTO metrics (metric_id, evidence_id, jurisdiction, sector_or_cohort,
           period_start, period_end, metric_label_raw, classification_dimension, numerator,
           denominator, denominator_definition, raw_value, numeric_value, unit, verification_status)
           VALUES ('pct-missing', 'ev-missing', 'Hong Kong', 'Public works contracts',
           '2025', '2025', 'Share', 'Accident type', NULL, NULL, '', '25%', 25, '%', 'Unverified')"""
    )
    connection.execute(
        """INSERT INTO metrics (metric_id, evidence_id, jurisdiction, sector_or_cohort,
           period_start, period_end, metric_label_raw, classification_dimension, numerator,
           denominator, denominator_definition, raw_value, numeric_value, unit, verification_status)
           VALUES ('pct-valid', 'ev-valid', 'Hong Kong', 'Public works contracts',
           '2025', '2025', 'Share', 'Accident type', 1, 4, 'cases', '25%', 25, '%', 'Unverified')"""
    )

    findings = metric_issues(connection)
    missing_issues = [item["issue"] for item in findings if item["metric_id"] == "pct-missing"]
    valid_issues = [item for item in findings if item["metric_id"] == "pct-valid"]
    assert any("Percentage requires a non-zero denominator" in issue for issue in missing_issues)
    assert valid_issues == []


def test_grouped_percentages_over_100_warn_about_multiple_responses(db):
    connection, source_version_id = db
    for metric_id, category, value in (("pct-a", "A", 60), ("pct-b", "B", 50)):
        evidence_id = f"ev-{metric_id}"
        connection.execute(
            """INSERT INTO evidence (evidence_id, source_version_id, page_or_section,
               exact_quote_or_excerpt, locator_type, extraction_method, review_status,
               confidence, created_at) VALUES (?, ?, ?, 'category', 'table row', 'fixture',
               'Unreviewed', 'high', '2026-01-01T00:00:00+00:00')""",
            (evidence_id, source_version_id, category),
        )
        connection.execute(
            """INSERT INTO metrics (metric_id, evidence_id, jurisdiction, sector_or_cohort,
               period_start, period_end, metric_label_raw, classification_dimension, numerator,
               denominator, denominator_definition, raw_value, numeric_value, unit, verification_status)
               VALUES (?, ?, 'Hong Kong', 'Public works contracts', '2025', '2025', ?,
               'Unsafe action', ?, 100, 'coded records', ?, ?, '%', 'Unverified')""",
            (metric_id, evidence_id, category, value, f"{value}%", value),
        )

    findings = metric_issues(connection)
    warnings = [item for item in findings if item["severity"] == "Warning"]
    assert len(warnings) == 1
    assert warnings[0]["metric_id"] == "pct-a, pct-b"
    assert "multiple responses" in warnings[0]["issue"]
    assert "110.00%" in warnings[0]["issue"]
