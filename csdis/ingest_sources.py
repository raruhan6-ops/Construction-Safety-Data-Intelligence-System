"""Explicit CLI for registering and retrieving selected seeded sources."""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

from csdis.database import connect
from csdis.ingestion import extract_devb_appendix_a, extract_devb_appendices, extract_devb_live_rates, extract_html_evidence, extract_html_tables, extract_ombudsman_di464_metrics, extract_pdf_evidence, extract_pdf_tables
from csdis.seed import import_seed_registry
from csdis.sources import download_source_version


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "local" / "csdis.sqlite3"
RAW_DIR = ROOT / "data" / "raw"
SEED_PATH = ROOT / "CSDIS_Seed_Source_Registry.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Retrieve explicitly selected public sources into the local CSDIS library.")
    parser.add_argument("--source-id", action="append", required=True,
                        help="Seed source ID to retrieve. Repeat the option to select more than one.")
    args = parser.parse_args()

    connection = connect(DB_PATH)
    try:
        added, errors = import_seed_registry(SEED_PATH, connection)
        print(f"Seed registry: {added} added, {errors} invalid row(s).")
        failed = 0
        for position, source_id in enumerate(args.source_id):
            source = connection.execute("SELECT title FROM sources WHERE source_id=?", (source_id,)).fetchone()
            if source is None:
                print(f"{source_id}: not present in the imported seed registry.", file=sys.stderr)
                failed += 1
                continue
            try:
                version_id, created, relative_path, status = download_source_version(
                    connection, RAW_DIR, source_id,
                )
                print(f"{source_id}: HTTP {status}; {'stored' if created else 'already stored'} {version_id} ({relative_path}).")
                version = connection.execute(
                    "SELECT original_filename, content_type FROM source_versions WHERE source_version_id=?",
                    (version_id,),
                ).fetchone()
                local_path = RAW_DIR / relative_path
                if version["content_type"] == "application/pdf" or version["original_filename"].lower().endswith(".pdf"):
                    text_pages, blank_pages = extract_pdf_evidence(local_path, version_id, connection)
                    table_rows = extract_pdf_tables(local_path, version_id, connection)
                    print(f"  PDF extraction: {text_pages} text pages, {blank_pages} pages without text, {table_rows} new candidate rows.")
                    if source_id == "S002":
                        appendix_a_metrics = extract_devb_appendix_a(local_path, version_id, connection)
                        metrics_added = extract_devb_appendices(local_path, version_id, connection)
                        print(f"  Appendix A: {appendix_a_metrics}; Appendices H–O: {metrics_added} new unverified metric records.")
                    elif source_id == "S012":
                        metrics_added = extract_ombudsman_di464_metrics(version_id, connection)
                        print(f"  DI/464 fatal accident tables: {metrics_added} new unverified, context-only metrics.")
                elif version["content_type"] == "text/html" or version["original_filename"].lower().endswith((".html", ".htm")):
                    evidence_count = extract_html_evidence(local_path, version_id, connection)
                    html_rows = extract_html_tables(local_path, version_id, connection)
                    print(f"  HTML extraction: {evidence_count} provisional evidence records, {html_rows} candidate table rows.")
                    if source_id == "S003":
                        live_metrics = extract_devb_live_rates(local_path, version_id, connection)
                        print(f"  DEVB live rates: {live_metrics} new unverified metrics; conflicts remain open.")
            except Exception as exc:
                failed += 1
                print(f"{source_id}: retrieval or extraction error: {exc}", file=sys.stderr)
            if position < len(args.source_id) - 1:
                time.sleep(1.0)
        return 1 if failed else 0
    finally:
        connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
