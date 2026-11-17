"""Streamlit entry point for the local CSDIS analyst workspace."""

from __future__ import annotations

import sqlite3
import json
import hashlib
import re
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from csdis.database import audit, connect, now_iso, table_count
from csdis.backup import create_backup_archive
from csdis.ingestion import (
    extract_csv_rows,
    extract_devb_appendix_a,
    extract_docx_tables,
    extract_devb_appendices,
    extract_devb_live_rates,
    extract_html_evidence,
    extract_html_tables,
    extract_ombudsman_di464_metrics,
    extract_pdf_evidence,
    extract_pdf_tables,
    extract_xlsx_rows,
    set_evidence_review,
    set_table_row_review,
)
from csdis.literature import export_bibtex, export_ris, review_literature_record, search_crossref, search_openalex, store_full_text
from csdis.schemas import CoverageMapping, PolicyEvent, SourceRecord, TechnologyModule
from csdis.seed import import_seed_registry
from csdis.sources import add_source, download_source_version, store_source_version, verify_source_version
from csdis.validation import detect_metric_conflicts, metric_issues


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data" / "local"
RAW_DIR = ROOT / "data" / "raw"
LITERATURE_FULLTEXT_DIR = ROOT / "data" / "literature" / "full_text"
DB_PATH = DATA_DIR / "csdis.sqlite3"
SEED_PATH = ROOT / "CSDIS_Seed_Source_Registry.csv"

st.set_page_config(page_title="CSDIS Research Workspace", page_icon="🦺", layout="wide")


@st.cache_resource
def get_connection() -> sqlite3.Connection:
    connection = connect(DB_PATH)
    if SEED_PATH.exists():
        import_seed_registry(SEED_PATH, connection)
    return connection


conn = get_connection()
st.title("CSDIS · Research Workspace")
st.caption("Local-first source registry and evidence foundation for construction safety research.")

sources_count = table_count(conn, "sources")
versions_count = table_count(conn, "source_versions")
evidence_count = table_count(conn, "evidence")
errors_count = table_count(conn, "seed_import_errors")
conflicts_count = conn.execute("SELECT COUNT(*) FROM conflicts WHERE status='Open'").fetchone()[0]
table_row_count = table_count(conn, "extracted_table_rows")
metrics = st.columns(6)
metrics[0].metric("Registered sources", sources_count)
metrics[1].metric("Immutable file versions", versions_count)
metrics[2].metric("Evidence records", evidence_count)
metrics[3].metric("Candidate table rows", table_row_count)
metrics[4].metric("Open conflicts", conflicts_count)
metrics[5].metric("Seed import issues", errors_count)

tab_home, tab_sources_group, tab_review_group, tab_research_group, tab_project_group = st.tabs(
    ["Start here", "Sources", "Review data", "Research tools", "Project tools"]
)

with tab_home:
    st.subheader("A simple path through CSDIS")
    st.markdown(
        "1. **Find or add sources** in Sources.\n"
        "2. **Check passages and table rows** in Review data > Evidence review.\n"
        "3. **Record and validate values** in Review data > Metrics.\n"
        "4. **Resolve disagreements** in Review data > Conflicts.\n\n"
        "Policy and technology coding, literature screening, audit history, and backups are available under Research tools and Project tools."
    )
    st.info("Research records begin as drafts. Check each value against its original source before treating it as verified. A recorded requirement does not by itself show that a site installed or used a system. See the relevant review status before citing findings.")

with tab_sources_group:
    source_tab, upload_tab = st.tabs(["Browse sources", "Add or upload a source"])
    with source_tab:
        st.subheader("Seeded and registered sources")
        rows = conn.execute(
            """SELECT s.source_id, s.publisher, s.title, s.source_type, s.canonical_url,
               s.format, s.authority_tier, s.data_period, s.origin,
               COUNT(v.source_version_id) AS versions
               FROM sources s LEFT JOIN source_versions v ON v.source_id=s.source_id
               GROUP BY s.source_id ORDER BY s.source_id"""
        ).fetchall()
        source_frame = pd.DataFrame([dict(row) for row in rows])
        st.dataframe(source_frame, use_container_width=True, hide_index=True)
        st.download_button("Download source register CSV", source_frame.to_csv(index=False).encode("utf-8-sig"),
                           "csdis_source_register.csv", "text/csv")
        source_details = conn.execute("SELECT source_id, title FROM sources ORDER BY source_id").fetchall()
        if source_details:
            source_labels = {f"{row['source_id']} — {row['title']}": row["source_id"] for row in source_details}
            detail_label = st.selectbox("Inspect source versions", list(source_labels), key="source_detail")
            detail_source_id = source_labels[detail_label]
            version_rows = conn.execute(
                """SELECT source_version_id, version_label, original_filename, storage_path,
                   sha256, file_size, content_type, retrieved_at, retrieval_method, http_status
                   FROM source_versions WHERE source_id=? ORDER BY retrieved_at DESC""",
                (detail_source_id,),
            ).fetchall()
            if version_rows:
                st.dataframe(pd.DataFrame([dict(row) for row in version_rows]), use_container_width=True, hide_index=True)
                version_labels = {
                    f"{row['source_version_id']} · {row['original_filename']} · {row['retrieved_at']}": row
                    for row in version_rows
                }
                selected_version_label = st.selectbox("Open immutable version", list(version_labels), key="version_detail")
                selected_version = version_labels[selected_version_label]
                stored_path = RAW_DIR / selected_version["storage_path"]
                if stored_path.is_file():
                    st.download_button("Download original source file", stored_path.read_bytes(),
                                       selected_version["original_filename"], selected_version["content_type"])
                else:
                    st.error("The database references a source file that is missing from data/raw.")
                if st.button("Verify this version's SHA-256"):
                    try:
                        valid, actual_hash = verify_source_version(conn, RAW_DIR, selected_version["source_version_id"])
                        if valid:
                            st.success(f"Checksum matches: {actual_hash}")
                        else:
                            st.error(f"Checksum mismatch or missing file. Current value: {actual_hash}")
                    except Exception as exc:
                        st.error(f"Could not verify checksum: {exc}")
            else:
                st.info("This source has no stored file versions yet.")
        if errors_count:
            with st.expander("Seed import issues"):
                issue_rows = conn.execute(
                    "SELECT row_number, source_id, error, raw_row_json FROM seed_import_errors ORDER BY error_id DESC"
                ).fetchall()
                st.dataframe(pd.DataFrame([dict(row) for row in issue_rows]), use_container_width=True, hide_index=True)

    with upload_tab:
        st.subheader("Register a source")
        with st.form("add_source_form", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            source_id = col_a.text_input("Source ID", placeholder="e.g. S015")
            publisher = col_b.text_input("Publisher")
            title = st.text_input("Title")
            source_type = st.text_input("Source type", value="Research source")
            canonical_url = st.text_input("Canonical URL or local reference")
            col_c, col_d = st.columns(2)
            file_format = col_c.text_input("Format", value="PDF")
            authority = col_d.selectbox("Authority tier", ["Primary", "Official guidance", "Peer-reviewed", "Secondary", "Unknown"])
            expected_data = st.text_area("Expected data / notes")
            submitted = st.form_submit_button("Register source")
            if submitted:
                try:
                    record = SourceRecord(
                        source_id=source_id.strip(), publisher=publisher.strip(), title=title.strip(),
                        source_type=source_type.strip(), canonical_url=canonical_url.strip(),
                        format=file_format.strip(), authority_tier=authority,
                        expected_data=expected_data.strip(),
                    )
                    if add_source(conn, record):
                        st.success(f"Registered {record.source_id}.")
                        st.rerun()
                    else:
                        st.error(f"Source ID {record.source_id} already exists. Existing record was left unchanged.")
                except Exception as exc:  # Pydantic validation should be readable in the UI.
                    st.error(f"Could not register source: {exc}")

        st.subheader("Upload a source file")
        source_rows = conn.execute("SELECT source_id, title FROM sources ORDER BY source_id").fetchall()
        if source_rows:
            source_options = {f"{row['source_id']} — {row['title']}": row["source_id"] for row in source_rows}
            download_label = st.selectbox("Registered public source to fetch", list(source_options), key="download_source")
            st.caption("Fetches are user-triggered, limited to 100 MiB, and use ordinary public HTTP(S) access. No login or access-control bypass is attempted.")
            if st.button("Download latest source version"):
                try:
                    source_id_to_fetch = source_options[download_label]
                    version_id, created, relative_path, status_code = download_source_version(
                        conn, RAW_DIR, source_id_to_fetch,
                    )
                    if created:
                        st.success(f"HTTP {status_code}: stored immutable version {version_id}.")
                    else:
                        st.info(f"HTTP {status_code}: identical content is already stored as {version_id}.")
                    stored_version = conn.execute(
                        "SELECT original_filename, content_type FROM source_versions WHERE source_version_id=?",
                        (version_id,),
                    ).fetchone()
                    if stored_version and (stored_version["content_type"] == "application/pdf" or stored_version["original_filename"].lower().endswith(".pdf")):
                        try:
                            pages, blank_pages = extract_pdf_evidence(RAW_DIR / relative_path, version_id, conn)
                            candidate_rows = extract_pdf_tables(RAW_DIR / relative_path, version_id, conn)
                            st.info(f"PDF parsing found text on {pages} pages, {blank_pages} blank-text pages, and {candidate_rows} new candidate table rows.")
                            if source_id_to_fetch == "S002":
                                appendix_a_metrics = extract_devb_appendix_a(RAW_DIR / relative_path, version_id, conn)
                                metrics_added = extract_devb_appendices(RAW_DIR / relative_path, version_id, conn)
                                st.info(f"DEVB Appendix A created {appendix_a_metrics} new unverified records; Appendices H–O created {metrics_added}.")
                            elif source_id_to_fetch == "S012":
                                metrics_added = extract_ombudsman_di464_metrics(version_id, conn)
                                st.info(f"DI/464 fatal-accident tables created {metrics_added} unverified, context-only metric records.")
                        except Exception as exc:
                            st.warning(f"The source file was stored, but PDF extraction did not complete: {exc}")
                    elif stored_version and (stored_version["content_type"] == "text/html" or stored_version["original_filename"].lower().endswith((".html", ".htm"))):
                        try:
                            extracted_count = extract_html_evidence(RAW_DIR / relative_path, version_id, conn)
                            html_rows = extract_html_tables(RAW_DIR / relative_path, version_id, conn)
                            st.info(f"HTML extraction created {extracted_count} provisional heading/paragraph evidence records and {html_rows} candidate table rows.")
                            if source_id_to_fetch == "S003":
                                live_metrics = extract_devb_live_rates(RAW_DIR / relative_path, version_id, conn)
                                st.info(f"DEVB live historical table created {live_metrics} unverified metrics; comparable conflicts remain open for review.")
                        except Exception as exc:
                            st.warning(f"The source page was stored, but HTML extraction did not complete: {exc}")
                    elif stored_version and stored_version["original_filename"].lower().endswith(".csv"):
                        try:
                            rows_added = extract_csv_rows(RAW_DIR / relative_path, version_id, conn)
                            st.info(f"CSV extraction created {rows_added} new provisional rows.")
                        except Exception as exc:
                            st.warning(f"The source file was stored, but CSV extraction did not complete: {exc}")
                    elif stored_version and stored_version["original_filename"].lower().endswith(".xlsx"):
                        try:
                            rows_added = extract_xlsx_rows(RAW_DIR / relative_path, version_id, conn)
                            st.info(f"Workbook extraction created {rows_added} new provisional rows.")
                        except Exception as exc:
                            st.warning(f"The source file was stored, but workbook extraction did not complete: {exc}")
                    elif stored_version and stored_version["original_filename"].lower().endswith(".docx"):
                        try:
                            rows_added = extract_docx_tables(RAW_DIR / relative_path, version_id, conn)
                            st.info(f"Word table extraction created {rows_added} new provisional rows.")
                        except Exception as exc:
                            st.warning(f"The source file was stored, but Word table extraction did not complete: {exc}")
                except Exception as exc:
                    st.error(f"Source download failed and was recorded: {exc}")

            fetch_attempts = conn.execute(
                """SELECT attempted_at, outcome, http_status, content_type, bytes_received, error_message
                   FROM source_fetch_attempts WHERE source_id=? ORDER BY attempted_at DESC LIMIT 10""",
                (source_options[download_label],),
            ).fetchall()
            if fetch_attempts:
                with st.expander("Recent download attempts"):
                    st.dataframe(pd.DataFrame([dict(row) for row in fetch_attempts]), use_container_width=True, hide_index=True)

            selected_label = st.selectbox("Attach file to source", list(source_options))
            upload = st.file_uploader("Choose a source document", type=None)
            if upload is not None and st.button("Store immutable source version"):
                try:
                    version_id, created, relative_path = store_source_version(
                        conn, RAW_DIR, source_options[selected_label], upload.name,
                        upload.getvalue(), upload.type or None,
                    )
                    if created:
                        st.success(f"Stored version {version_id} ({relative_path}).")
                    else:
                        st.info(f"This exact file is already stored as {version_id}; no duplicate was created.")
                    try:
                        if upload.name.lower().endswith(".pdf"):
                            pages, blank_pages = extract_pdf_evidence(RAW_DIR / relative_path, version_id, conn)
                            candidate_rows = extract_pdf_tables(RAW_DIR / relative_path, version_id, conn)
                            st.info(f"PDF evidence available on {pages} pages. {blank_pages} pages had no extractable text; {candidate_rows} candidate table rows were stored as raw cells for review.")
                            if source_options[selected_label] == "S002":
                                appendix_a_metrics = extract_devb_appendix_a(RAW_DIR / relative_path, version_id, conn)
                                metrics_added = extract_devb_appendices(RAW_DIR / relative_path, version_id, conn)
                                st.info(f"DEVB Appendix A created {appendix_a_metrics} new unverified records; Appendices H–O created {metrics_added}.")
                            elif source_options[selected_label] == "S012":
                                metrics_added = extract_ombudsman_di464_metrics(version_id, conn)
                                st.info(f"DI/464 fatal-accident tables created {metrics_added} unverified, context-only metric records.")
                        elif (upload.type or "").split(";")[0] == "text/html" or upload.name.lower().endswith((".html", ".htm")):
                            extracted_count = extract_html_evidence(RAW_DIR / relative_path, version_id, conn)
                            html_rows = extract_html_tables(RAW_DIR / relative_path, version_id, conn)
                            st.info(f"HTML extraction created {extracted_count} provisional heading/paragraph evidence records and {html_rows} candidate table rows.")
                            if source_options[selected_label] == "S003":
                                live_metrics = extract_devb_live_rates(RAW_DIR / relative_path, version_id, conn)
                                st.info(f"DEVB live historical table created {live_metrics} unverified metrics; comparable conflicts remain open for review.")
                        elif upload.name.lower().endswith(".csv"):
                            rows_added = extract_csv_rows(RAW_DIR / relative_path, version_id, conn)
                            st.info(f"CSV extraction created {rows_added} new provisional rows.")
                        elif upload.name.lower().endswith(".xlsx"):
                            rows_added = extract_xlsx_rows(RAW_DIR / relative_path, version_id, conn)
                            st.info(f"Workbook extraction created {rows_added} new provisional rows.")
                        elif upload.name.lower().endswith(".docx"):
                            rows_added = extract_docx_tables(RAW_DIR / relative_path, version_id, conn)
                            st.info(f"Word table extraction created {rows_added} new provisional rows.")
                    except Exception as exc:
                        st.warning(f"The file was stored, but document extraction did not complete: {exc}")
                except Exception as exc:
                    st.error(f"Upload failed: {exc}")
        else:
            st.info("Register or import a source before uploading a file.")

with tab_review_group:
    evidence_tab, metrics_tab, conflicts_tab = st.tabs(["Evidence review", "Metrics", "Conflicts"])
    with evidence_tab:
        st.subheader("Evidence review")
        evidence_rows = conn.execute(
            """SELECT e.evidence_id, e.source_version_id, e.page_or_section,
               e.exact_quote_or_excerpt, e.locator_type, e.extraction_method,
               e.review_status, e.reviewer, e.confidence, e.metadata_json,
               s.title AS source_title, v.original_filename, v.storage_path, v.content_type
               FROM evidence e JOIN source_versions v ON v.source_version_id=e.source_version_id
               JOIN sources s ON s.source_id=v.source_id ORDER BY e.created_at DESC"""
        ).fetchall()
        if evidence_rows:
            evidence_frame = pd.DataFrame([dict(row) for row in evidence_rows])
            st.download_button("Download evidence ledger CSV", evidence_frame.to_csv(index=False).encode("utf-8-sig"),
                               "csdis_evidence_ledger.csv", "text/csv")
        if not evidence_rows:
            st.info("Upload a PDF or add evidence records to begin review. PDF page text is stored as provisional evidence; no OCR is run automatically.")
        else:
            evidence_options = {
                f"{row['evidence_id']} · {row['source_title']} · {row['page_or_section']} · {row['review_status']}": row
                for row in evidence_rows
            }
            chosen_label = st.selectbox("Select evidence", list(evidence_options))
            selected_evidence = evidence_options[chosen_label]
            st.caption(f"Source version: {selected_evidence['source_version_id']} · Method: {selected_evidence['extraction_method']} · Confidence: {selected_evidence['confidence']}")
            evidence_metadata = json.loads(selected_evidence["metadata_json"] or "{}")
            is_pdf = selected_evidence["content_type"] == "application/pdf" or selected_evidence["original_filename"].lower().endswith(".pdf")
            if is_pdf:
                page_number = evidence_metadata.get("page_number")
                if page_number is None:
                    page_match = re.search(r"PDF page (\d+)", selected_evidence["page_or_section"] or "", re.IGNORECASE)
                    page_number = int(page_match.group(1)) if page_match else None
                if page_number:
                    pdf_path = RAW_DIR / selected_evidence["storage_path"]
                    if pdf_path.is_file():
                        try:
                            import pdfplumber

                            with pdfplumber.open(pdf_path) as pdf_document:
                                if 1 <= int(page_number) <= len(pdf_document.pages):
                                    with st.expander(f"Original PDF page {page_number}", expanded=True):
                                        st.image(pdf_document.pages[int(page_number) - 1].to_image(resolution=100).original,
                                                 caption=f"{selected_evidence['original_filename']} · page {page_number}",
                                                 use_container_width=True)
                        except Exception as exc:
                            st.caption(f"PDF preview is unavailable: {exc}")
            st.text_area("Extracted source text (retained as captured)", selected_evidence["exact_quote_or_excerpt"], height=260, disabled=True)
            old_metadata = evidence_metadata
            reviewer_note = st.text_input("Reviewer note", value=old_metadata.get("review_note", ""), key="evidence_note")
            reviewer = st.text_input("Reviewer", value=selected_evidence["reviewer"] or "", key="evidence_reviewer")
            review_status = st.selectbox("Decision", ["Unreviewed", "Human-verified", "Ambiguous", "Rejected"],
                                         index=["Unreviewed", "Human-verified", "Ambiguous", "Rejected"].index(selected_evidence["review_status"])
                                         if selected_evidence["review_status"] in ["Unreviewed", "Human-verified", "Ambiguous", "Rejected"] else 0)
            if st.button("Save evidence review"):
                try:
                    set_evidence_review(conn, selected_evidence["evidence_id"], review_status, reviewer, reviewer_note)
                    st.success("Review decision recorded in the audit trail.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save review: {exc}")

        st.subheader("Candidate table rows")
        table_rows = conn.execute(
            """SELECT r.row_id, r.source_version_id, r.page_number, r.table_index, r.row_index,
               r.raw_cells_json, r.review_status, r.reviewer, r.review_note, r.extracted_at,
               e.page_or_section AS source_locator,
               s.title AS source_title
               FROM extracted_table_rows r JOIN source_versions v ON v.source_version_id=r.source_version_id
               JOIN evidence e ON e.evidence_id=r.evidence_id
               JOIN sources s ON s.source_id=v.source_id ORDER BY r.extracted_at DESC, r.page_number"""
        ).fetchall()
        if table_rows:
            table_export = pd.DataFrame([dict(row) for row in table_rows])
            st.dataframe(table_export, use_container_width=True, hide_index=True)
            st.download_button("Download raw candidate rows CSV", table_export.to_csv(index=False).encode("utf-8-sig"),
                               "csdis_pdf_table_rows.csv", "text/csv")
            row_options = {f"{row['row_id']} · {row['source_title']} · {row['source_locator']} · {row['review_status']}": row for row in table_rows}
            row_label = st.selectbox("Candidate row to inspect", list(row_options))
            selected_row = row_options[row_label]
            st.json(json.loads(selected_row["raw_cells_json"]))
            row_note = st.text_input("Table row review note", value=selected_row["review_note"] or "", key="table_row_note")
            row_reviewer = st.text_input("Table row reviewer", value=selected_row["reviewer"] or "", key="table_row_reviewer")
            row_status_options = ["Unreviewed", "Human-verified", "Ambiguous", "Rejected"]
            row_status = st.selectbox("Table row decision", row_status_options,
                                      index=row_status_options.index(selected_row["review_status"])
                                      if selected_row["review_status"] in row_status_options else 0)
            if st.button("Save table row review"):
                try:
                    set_table_row_review(conn, selected_row["row_id"], row_status, row_reviewer, row_note)
                    st.success("Table row review recorded; raw cells were retained.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not save table row review: {exc}")
        else:
            st.info("No candidate table rows yet. PDF table parsing stores raw cell strings and leaves interpretation to the reviewer.")

    with metrics_tab:
        st.subheader("Metric records")
        metric_rows = conn.execute(
            """SELECT m.metric_id, m.jurisdiction, m.sector_or_cohort, m.period_start,
               m.period_end, m.metric_label_raw, m.metric_label_harmonised,
               m.classification_dimension, m.numerator,
               m.denominator, m.denominator_definition, m.raw_value, m.numeric_value,
               m.unit, m.rate_multiplier, m.formula, m.outcome_definition,
               m.comparability_status, m.comparability_note, m.verification_status,
               m.reviewer, m.review_note, m.evidence_id, e.page_or_section, v.source_id,
               s.title AS source_title, v.source_version_id, v.retrieved_at AS source_snapshot
               FROM metrics m JOIN evidence e ON e.evidence_id=m.evidence_id
               JOIN source_versions v ON v.source_version_id=e.source_version_id
               JOIN sources s ON s.source_id=v.source_id
               ORDER BY m.period_start, m.metric_id"""
        ).fetchall()
        if metric_rows:
            metric_records = [dict(row) for row in metric_rows]
            metric_frame = pd.DataFrame(metric_records)
            st.dataframe(metric_frame, use_container_width=True, hide_index=True)
            csv_data = metric_frame.to_csv(index=False).encode("utf-8-sig")
            st.download_button("Download metric records CSV", csv_data, "csdis_metrics.csv", "text/csv")
            source_versions = {}
            for row in metric_records:
                source_versions[row["source_version_id"]] = {
                    "source_id": row["source_id"], "source_title": row["source_title"],
                    "snapshot_at": row["source_snapshot"],
                }
            metric_manifest = {
                "manifest_version": 1,
                "created_at": now_iso(),
                "export": {"filename": "csdis_metrics.csv", "format": "CSV", "sha256": hashlib.sha256(csv_data).hexdigest()},
                "scope": "All metric records in the local database at export time",
                "metric_count": len(metric_records),
                "metric_ids": [row["metric_id"] for row in metric_records],
                "source_versions": list(source_versions.values()),
                "limitations": "This manifest records provenance and export identity; it does not certify human review or cross-source comparability.",
            }
            st.download_button("Download metric export manifest", json.dumps(metric_manifest, indent=2, ensure_ascii=False).encode("utf-8"),
                               "csdis_metrics_manifest.json", "application/json")
        else:
            st.info("No metrics have been recorded. Enter a value only when its source evidence is available.")

        findings = metric_issues(conn)
        st.subheader("Validation findings")
        if findings:
            findings_frame = pd.DataFrame(findings)
            st.dataframe(findings_frame, use_container_width=True, hide_index=True)
            validation_report = {
                "report_version": 1,
                "generated_at": now_iso(),
                "scope": "Current metric validation checks across all records in the local database",
                "finding_count": len(findings),
                "findings": findings,
                "limitations": "Findings are screening prompts. They do not resolve source conflicts or replace researcher review.",
            }
            st.download_button("Download validation report JSON",
                               json.dumps(validation_report, indent=2, ensure_ascii=False, default=str).encode("utf-8"),
                               "csdis_validation_report.json", "application/json")
        else:
            st.success("No arithmetic or denominator issues detected in current metric records.")

        reviewed_table_rows = conn.execute(
            """SELECT r.row_id, r.evidence_id, r.page_number, r.table_index, r.row_index,
               r.raw_cells_json, s.title AS source_title, e.page_or_section AS source_locator
               FROM extracted_table_rows r JOIN source_versions v ON v.source_version_id=r.source_version_id
               JOIN evidence e ON e.evidence_id=r.evidence_id
               JOIN sources s ON s.source_id=v.source_id
               WHERE r.review_status='Human-verified' ORDER BY s.title, r.page_number, r.table_index, r.row_index"""
        ).fetchall()
        if reviewed_table_rows:
            st.subheader("Create a metric from a reviewed table row")
            reviewed_row_labels = {
                f"{row['row_id']} · {row['source_title']} · {row['source_locator']}": row
                for row in reviewed_table_rows
            }
            reviewed_row_label = st.selectbox("Verified source row", list(reviewed_row_labels), key="metric_source_row")
            reviewed_row = reviewed_row_labels[reviewed_row_label]
            raw_cells = json.loads(reviewed_row["raw_cells_json"])
            st.json(raw_cells)
            cell_options = [index for index, value in enumerate(raw_cells) if value is not None and str(value).strip()]
            if len(cell_options) >= 2:
                cell_label = {index: f"Column {index + 1}: {raw_cells[index]}" for index in cell_options}
                with st.form("metric_from_table_row_form", clear_on_submit=True):
                    st.caption("Choose source cells explicitly. The selected raw strings are retained in the metric record.")
                    label_column = st.selectbox("Cell containing the published metric label", cell_options,
                                                format_func=lambda index: cell_label[index])
                    value_column = st.selectbox("Cell containing the published value", cell_options,
                                                index=min(1, len(cell_options) - 1),
                                                format_func=lambda index: cell_label[index])
                    a, b = st.columns(2)
                    row_jurisdiction = a.selectbox("Jurisdiction", ["Hong Kong", "Singapore", "Cross-country"], key="row_metric_jurisdiction")
                    row_cohort = b.text_input("Sector or cohort", key="row_metric_cohort")
                    a, b = st.columns(2)
                    row_period_start = a.text_input("Period start", key="row_metric_period_start")
                    row_period_end = b.text_input("Period end", key="row_metric_period_end")
                    row_dimension = st.selectbox("Classification dimension", ["Accident type", "Agent", "Unsafe action", "Unsafe condition", "Personal factor", "Injury nature", "Body part", "Trade", "Rate", "Severity", "Exposure", "Other"], key="row_metric_dimension")
                    a, b = st.columns(2)
                    row_numerator = a.text_input("Numerator (if applicable)", key="row_metric_numerator")
                    row_denominator = b.text_input("Denominator (if applicable)", key="row_metric_denominator")
                    row_denominator_definition = st.text_input("Denominator meaning", key="row_metric_denominator_meaning")
                    a, b = st.columns(2)
                    row_numeric_value = a.text_input("Parsed numeric value (if safely numeric)", key="row_metric_numeric")
                    row_unit = b.text_input("Unit", key="row_metric_unit")
                    create_row_metric = st.form_submit_button("Create unverified metric")
                    if create_row_metric:
                        try:
                            if label_column == value_column:
                                raise ValueError("Choose separate cells for label and value.")
                            if not row_cohort.strip() or not row_period_start.strip() or not row_period_end.strip() or not row_unit.strip():
                                raise ValueError("Cohort, period and unit are required.")
                            def row_optional_number(value: str) -> float | None:
                                return float(value.strip()) if value.strip() else None

                            metric_id = "metric-" + uuid.uuid4().hex[:16]
                            with conn:
                                conn.execute("""INSERT INTO metrics (metric_id, evidence_id, jurisdiction,
                                    sector_or_cohort, period_start, period_end, metric_label_raw,
                                    classification_dimension, numerator, denominator, denominator_definition,
                                    raw_value, numeric_value, unit, verification_status)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Unverified')""",
                                    (metric_id, reviewed_row["evidence_id"], row_jurisdiction, row_cohort.strip(),
                                     row_period_start.strip(), row_period_end.strip(), str(raw_cells[label_column]),
                                     row_dimension, row_optional_number(row_numerator), row_optional_number(row_denominator),
                                     row_denominator_definition.strip(), str(raw_cells[value_column]),
                                     row_optional_number(row_numeric_value), row_unit.strip()))
                                audit(conn, "metric_created_from_table_row", "metric", metric_id,
                                      {"row_id": reviewed_row["row_id"], "evidence_id": reviewed_row["evidence_id"],
                                       "label_column": label_column, "value_column": value_column,
                                       "status": "Unverified"})
                                found_conflicts = detect_metric_conflicts(conn, metric_id)
                            message = f"Created {metric_id} with raw label/value from the reviewed source row. It remains unverified."
                            if found_conflicts:
                                message += f" Flagged {len(found_conflicts)} unresolved source conflict(s)."
                            st.success(message)
                            st.rerun()
                        except (ValueError, sqlite3.Error) as exc:
                            st.error(f"Could not create metric: {exc}")
            else:
                st.info("This reviewed row has fewer than two nonblank cells and cannot supply both a label and value.")

        if evidence_rows:
            st.subheader("Add a metric linked to evidence")
            evidence_for_metric = {
                f"{row['evidence_id']} · {row['source_title']} · {row['page_or_section']}": row["evidence_id"]
                for row in evidence_rows
            }
            with st.form("metric_form", clear_on_submit=True):
                evidence_label = st.selectbox("Evidence locator", list(evidence_for_metric))
                a, b = st.columns(2)
                jurisdiction = a.selectbox("Jurisdiction", ["Hong Kong", "Singapore", "Cross-country"])
                cohort = b.text_input("Sector or cohort", placeholder="e.g. public works")
                a, b = st.columns(2)
                period_start = a.text_input("Period start", placeholder="2025")
                period_end = b.text_input("Period end", placeholder="2025")
                label = st.text_input("Metric label as published")
                dimension = st.selectbox("Classification dimension", ["Accident type", "Agent", "Unsafe action", "Unsafe condition", "Personal factor", "Injury nature", "Body part", "Trade", "Rate", "Severity", "Exposure", "Other"])
                outcome_definition = st.text_input("Outcome definition", placeholder="e.g. fatal and major injury incidents")
                comparability_status = st.selectbox("Comparability", ["Unassessed", "Comparable within source series", "Comparable candidates", "Context only", "Not comparable"])
                comparability_note = st.text_input("Comparison note", placeholder="e.g. differs by cohort or outcome definition")
                a, b = st.columns(2)
                numerator_text = a.text_input("Numerator (if applicable)")
                denominator_text = b.text_input("Denominator (if applicable)")
                denominator_definition = st.text_input("Denominator meaning", placeholder="e.g. coded personal-factor records")
                a, b = st.columns(2)
                raw_value = a.text_input("Raw published value", help="Preserve dashes, footnotes and displayed rounding.")
                numeric_text = b.text_input("Parsed numeric value (if safely numeric)")
                unit = st.text_input("Unit", placeholder="percent, accidents, accidents per 1,000 workers")
                submitted_metric = st.form_submit_button("Save metric")
                if submitted_metric:
                    try:
                        def optional_number(value: str) -> float | None:
                            return float(value.strip()) if value.strip() else None

                        values = (optional_number(numerator_text), optional_number(denominator_text), optional_number(numeric_text))
                        if not cohort.strip() or not period_start.strip() or not period_end.strip() or not label.strip() or not raw_value.strip() or not unit.strip():
                            raise ValueError("Cohort, period, label, raw value and unit are required.")
                        metric_id = "metric-" + uuid.uuid4().hex[:16]
                        with conn:
                            conn.execute(
                                """INSERT INTO metrics (metric_id, evidence_id, jurisdiction, sector_or_cohort,
                                   period_start, period_end, metric_label_raw, classification_dimension,
                                   outcome_definition, comparability_status, comparability_note,
                                   numerator, denominator, denominator_definition, raw_value, numeric_value,
                                   unit, verification_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (metric_id, evidence_for_metric[evidence_label], jurisdiction, cohort.strip(),
                                 period_start.strip(), period_end.strip(), label.strip(), dimension,
                                 outcome_definition.strip(), comparability_status, comparability_note.strip(),
                                 values[0], values[1], denominator_definition.strip(), raw_value,
                                 values[2], unit.strip(), "Unverified"),
                            )
                            audit(conn, "metric_created", "metric", metric_id,
                                  {"evidence_id": evidence_for_metric[evidence_label], "status": "Unverified"})
                            found_conflicts = detect_metric_conflicts(conn, metric_id)
                        message = f"Saved metric {metric_id}; it remains linked to its evidence locator."
                        if found_conflicts:
                            message += f" Flagged {len(found_conflicts)} unresolved source conflict(s)."
                        st.success(message)
                        st.rerun()
                    except (ValueError, sqlite3.Error) as exc:
                        st.error(f"Could not save metric: {exc}")

        if metric_rows:
            st.subheader("Review a metric")
            review_options = {f"{row['metric_id']} · {row['metric_label_raw']} = {row['raw_value']} · {row['verification_status']}": row for row in metric_rows}
            metric_label = st.selectbox("Metric to review", list(review_options))
            selected_metric = review_options[metric_label]
            metric_reviewer = st.text_input("Reviewer name or initials", key="metric_reviewer")
            metric_note = st.text_area("Review reason or note", key="metric_review_note")
            metric_status = st.selectbox("Review outcome", ["Unverified", "Arithmetic checked", "Source checked", "Human verified", "Conflict", "Excluded"], key="metric_review_status")
            if st.button("Save metric review"):
                if metric_status != "Unverified" and (not metric_reviewer.strip() or not metric_note.strip()):
                    st.error("A reviewer and reason are required for a verification decision.")
                else:
                    with conn:
                        conn.execute("UPDATE metrics SET verification_status=?, reviewer=?, review_note=?, reviewed_at=? WHERE metric_id=?",
                                     (metric_status, metric_reviewer.strip() or None, metric_note.strip() or None,
                                      now_iso() if metric_status != "Unverified" else None, selected_metric["metric_id"]))
                        audit(conn, "metric_reviewed", "metric", selected_metric["metric_id"],
                              {"status": metric_status, "reviewer": metric_reviewer.strip(), "note": metric_note.strip()})
                    st.success("Metric review decision saved.")
                    st.rerun()

    with conflicts_tab:
        st.subheader("Source discrepancy register")
        conflict_rows = conn.execute(
            """SELECT c.conflict_id, c.severity, c.status, c.description, c.created_at,
               a.metric_label_raw AS metric_a, a.raw_value AS value_a, a.evidence_id AS evidence_a,
               va.source_version_id AS source_version_a, va.retrieved_at AS snapshot_a,
               ea.page_or_section AS locator_a, sa.title AS source_a, sa.canonical_url AS url_a,
               b.metric_label_raw AS metric_b, b.raw_value AS value_b, b.evidence_id AS evidence_b,
               vb.source_version_id AS source_version_b, vb.retrieved_at AS snapshot_b,
               eb.page_or_section AS locator_b, sb.title AS source_b, sb.canonical_url AS url_b,
               c.reviewer, c.resolution_note
               FROM conflicts c JOIN metrics a ON a.metric_id=c.metric_a_id
               JOIN metrics b ON b.metric_id=c.metric_b_id
               JOIN evidence ea ON ea.evidence_id=a.evidence_id JOIN source_versions va ON va.source_version_id=ea.source_version_id
               JOIN sources sa ON sa.source_id=va.source_id
               JOIN evidence eb ON eb.evidence_id=b.evidence_id JOIN source_versions vb ON vb.source_version_id=eb.source_version_id
               JOIN sources sb ON sb.source_id=vb.source_id ORDER BY c.created_at DESC"""
        ).fetchall()
        if conflict_rows:
            st.dataframe(pd.DataFrame([dict(row) for row in conflict_rows]), use_container_width=True, hide_index=True)
            st.download_button("Download conflict register CSV", pd.DataFrame([dict(row) for row in conflict_rows]).to_csv(index=False).encode("utf-8-sig"),
                               "csdis_conflicts.csv", "text/csv")
        else:
            st.info("No conflicts recorded. Conflicting values should remain separate metric records until reviewed.")
        metric_choices = conn.execute("SELECT metric_id, metric_label_raw, raw_value, evidence_id FROM metrics ORDER BY metric_id").fetchall()
        if len(metric_choices) >= 2:
            metric_labels = {f"{r['metric_id']} · {r['metric_label_raw']} = {r['raw_value']} · {r['evidence_id']}": r['metric_id'] for r in metric_choices}
            with st.form("conflict_form", clear_on_submit=True):
                label_a = st.selectbox("First metric", list(metric_labels), key="conflict_a")
                label_b = st.selectbox("Second metric", list(metric_labels), key="conflict_b")
                severity = st.selectbox("Severity", ["Low", "Medium", "High"])
                description = st.text_area("Why the records may conflict; preserve scope/definition differences")
                create_conflict = st.form_submit_button("Record unresolved conflict")
                if create_conflict:
                    id_a, id_b = metric_labels[label_a], metric_labels[label_b]
                    if id_a == id_b:
                        st.error("Choose two different metric records.")
                    elif not description.strip():
                        st.error("Add a short description to preserve the reason for the conflict.")
                    elif conn.execute("SELECT 1 FROM conflicts WHERE (metric_a_id=? AND metric_b_id=?) OR (metric_a_id=? AND metric_b_id=?)", (id_a, id_b, id_b, id_a)).fetchone():
                        st.error("A conflict record already exists for those two metrics.")
                    else:
                        conflict_id = "conflict-" + uuid.uuid4().hex[:16]
                        with conn:
                            conn.execute("INSERT INTO conflicts (conflict_id, metric_a_id, metric_b_id, severity, status, description, created_at) VALUES (?, ?, ?, ?, 'Open', ?, ?)",
                                         (conflict_id, id_a, id_b, severity, description.strip(), now_iso()))
                            audit(conn, "conflict_created", "conflict", conflict_id,
                                  {"metric_a_id": id_a, "metric_b_id": id_b, "severity": severity})
                        st.success(f"Recorded {conflict_id} as unresolved.")
                        st.rerun()
        open_conflicts = conn.execute("SELECT conflict_id, description FROM conflicts WHERE status='Open' ORDER BY created_at").fetchall()
        if open_conflicts:
            st.subheader("Adjudicate or report a conflict")
            conflict_options = {f"{row['conflict_id']} · {row['description']}": row["conflict_id"] for row in open_conflicts}
            chosen_conflict_label = st.selectbox("Open conflict", list(conflict_options))
            conflict_reviewer = st.text_input("Conflict reviewer", key="conflict_reviewer")
            resolution_note = st.text_area("Adjudication or reporting note", key="conflict_resolution")
            resolution_status = st.selectbox("Outcome", ["Adjudicated", "Reported unresolved"], key="conflict_outcome")
            if st.button("Save conflict outcome"):
                if not conflict_reviewer.strip() or not resolution_note.strip():
                    st.error("Reviewer and an outcome note are required.")
                else:
                    conflict_id = conflict_options[chosen_conflict_label]
                    with conn:
                        conn.execute("UPDATE conflicts SET status=?, reviewer=?, resolution_note=? WHERE conflict_id=?",
                                     (resolution_status, conflict_reviewer.strip(), resolution_note.strip(), conflict_id))
                        audit(conn, "conflict_adjudicated", "conflict", conflict_id,
                              {"status": resolution_status, "reviewer": conflict_reviewer.strip(), "note": resolution_note.strip()})
                    st.success("Conflict outcome saved. The two source values remain preserved.")
                    st.rerun()

with tab_research_group:
    policy_tab, literature_tab = st.tabs(["Policy and coverage", "Literature"])
    with policy_tab:
        st.subheader("Policy events")
        policy_rows = conn.execute("""SELECT p.*, e.page_or_section FROM policy_events p
            JOIN evidence e ON e.evidence_id=p.evidence_id ORDER BY p.effective_from, p.policy_id""").fetchall()
        if policy_rows:
            policy_frame = pd.DataFrame([dict(row) for row in policy_rows])
            st.dataframe(policy_frame, use_container_width=True, hide_index=True)
            st.download_button("Download policy timeline CSV", policy_frame.to_csv(index=False).encode("utf-8-sig"),
                               "csdis_policy_timeline.csv", "text/csv")
        else:
            st.info("No policy events recorded. Add a policy event only when source evidence is available.")

        reviewable_policies = conn.execute("SELECT policy_id, instrument, review_status FROM policy_events WHERE review_status!='Human-verified' ORDER BY policy_id").fetchall()
        if reviewable_policies:
            st.markdown("**Review policy evidence and scope**")
            policy_review_labels = {f"{row['policy_id']} · {row['instrument']} · {row['review_status']}": row["policy_id"] for row in reviewable_policies}
            policy_review_label = st.selectbox("Policy event to review", list(policy_review_labels), key="policy_review_item")
            policy_reviewer = st.text_input("Policy reviewer", key="policy_reviewer")
            policy_review_note = st.text_area("Policy review note", key="policy_review_note")
            policy_review_outcome = st.selectbox("Policy review outcome", ["Human-verified", "Rejected", "Unreviewed"], key="policy_review_outcome")
            if st.button("Save policy review"):
                if policy_review_outcome == "Human-verified" and (not policy_reviewer.strip() or not policy_review_note.strip()):
                    st.error("A reviewer and note are required to verify a policy event.")
                else:
                    policy_id = policy_review_labels[policy_review_label]
                    linked_evidence = conn.execute("SELECT e.review_status FROM policy_events p JOIN evidence e ON e.evidence_id=p.evidence_id WHERE p.policy_id=?", (policy_id,)).fetchone()
                    if policy_review_outcome == "Human-verified" and linked_evidence and linked_evidence["review_status"] != "Human-verified":
                        st.error("Review and human-verify the linked source evidence before verifying this policy event.")
                    else:
                        with conn:
                            conn.execute("UPDATE policy_events SET review_status=?, reviewer=?, review_note=? WHERE policy_id=?",
                                         (policy_review_outcome, policy_reviewer.strip() or None, policy_review_note.strip() or None, policy_id))
                            audit(conn, "policy_event_reviewed", "policy", policy_id,
                                  {"status": policy_review_outcome, "reviewer": policy_reviewer.strip(), "note": policy_review_note.strip()})
                        st.success("Policy review recorded.")
                        st.rerun()

        if evidence_rows:
            evidence_labels = {f"{row['evidence_id']} · {row['source_title']} · {row['page_or_section']}": row["evidence_id"] for row in evidence_rows}
            with st.form("policy_event_form", clear_on_submit=True):
                st.markdown("**Add an evidence-linked policy event**")
                p_evidence_label = st.selectbox("Policy evidence", list(evidence_labels))
                a, b = st.columns(2)
                p_jurisdiction = a.selectbox("Jurisdiction", ["Hong Kong", "Singapore"])
                p_instrument = b.text_input("Instrument / source title")
                a, b = st.columns(2)
                p_announcement = a.text_input("Announcement date (YYYY-MM-DD, optional)")
                p_effective_from = b.text_input("Effective from (YYYY-MM-DD, optional)")
                a, b = st.columns(2)
                p_effective_to = a.text_input("Effective to (YYYY-MM-DD, optional)")
                p_threshold = b.text_input("Project threshold", placeholder="e.g. estimated contract sum exceeding 30 million")
                a, b = st.columns(2)
                p_currency = a.text_input("Currency", placeholder="HKD, SGD, or Not applicable")
                p_scope = b.text_input("Covered project type / work scope")
                p_status = st.selectbox("Policy status", ["Mandatory", "Selected mandatory module", "Encouraged", "Voluntary", "Pilot", "Unknown"])
                p_text = st.text_area("Faithful requirement description")
                p_supersedes = st.text_input("Supersedes policy ID (optional)")
                save_policy = st.form_submit_button("Save policy event")
                if save_policy:
                    try:
                        policy = PolicyEvent(
                            policy_id="policy-" + uuid.uuid4().hex[:16],
                            evidence_id=evidence_labels[p_evidence_label], jurisdiction=p_jurisdiction,
                            instrument=p_instrument.strip(), announcement_date=p_announcement.strip() or None,
                            effective_from=p_effective_from.strip() or None, effective_to=p_effective_to.strip() or None,
                            project_threshold=p_threshold.strip(), currency=p_currency.strip(),
                            covered_project_type=p_scope.strip(), mandatory_status=p_status,
                            requirement_text=p_text.strip(),
                        )
                        values = policy.model_dump(mode="json")
                        with conn:
                            conn.execute("""INSERT INTO policy_events (policy_id, evidence_id, jurisdiction,
                                instrument, announcement_date, effective_from, effective_to, project_threshold,
                                currency, covered_project_type, mandatory_status, requirement_text,
                                supersedes_policy_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (values["policy_id"], values["evidence_id"], values["jurisdiction"], values["instrument"],
                                 values["announcement_date"], values["effective_from"], values["effective_to"],
                                 values["project_threshold"], values["currency"], values["covered_project_type"],
                                 values["mandatory_status"], values["requirement_text"], p_supersedes.strip() or None, now_iso()))
                            audit(conn, "policy_event_created", "policy", values["policy_id"],
                                  {"evidence_id": values["evidence_id"], "status": "Unreviewed"})
                        st.success(f"Saved {values['policy_id']} as an evidence-linked, unreviewed event.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not save policy event: {exc}")

        st.subheader("Technology modules")
        module_rows = conn.execute("""SELECT t.*, e.page_or_section FROM technology_modules t
            JOIN evidence e ON e.evidence_id=t.evidence_id ORDER BY t.system_name, t.module_name""").fetchall()
        if module_rows:
            module_frame = pd.DataFrame([dict(row) for row in module_rows])
            st.dataframe(module_frame, use_container_width=True, hide_index=True)
            st.download_button("Download technology module registry CSV", module_frame.to_csv(index=False).encode("utf-8-sig"),
                               "csdis_technology_modules.csv", "text/csv")
        else:
            st.info("No technology modules recorded.")

        reviewable_modules = conn.execute("SELECT technology_id, system_name, module_name, review_status FROM technology_modules WHERE review_status!='Human-verified' ORDER BY system_name, module_name").fetchall()
        if reviewable_modules:
            st.markdown("**Review documented module function and status**")
            module_review_labels = {f"{row['technology_id']} · {row['system_name']} · {row['module_name']} · {row['review_status']}": row["technology_id"] for row in reviewable_modules}
            module_review_label = st.selectbox("Technology module to review", list(module_review_labels), key="module_review_item")
            module_reviewer = st.text_input("Module reviewer", key="module_reviewer")
            module_review_note = st.text_area("Module review note", key="module_review_note")
            module_review_outcome = st.selectbox("Module review outcome", ["Human-verified", "Rejected", "Unreviewed"], key="module_review_outcome")
            if st.button("Save module review"):
                if module_review_outcome == "Human-verified" and (not module_reviewer.strip() or not module_review_note.strip()):
                    st.error("A reviewer and note are required to verify a technology module.")
                else:
                    technology_id = module_review_labels[module_review_label]
                    linked_evidence = conn.execute("SELECT e.review_status FROM technology_modules t JOIN evidence e ON e.evidence_id=t.evidence_id WHERE t.technology_id=?", (technology_id,)).fetchone()
                    if module_review_outcome == "Human-verified" and linked_evidence and linked_evidence["review_status"] != "Human-verified":
                        st.error("Review and human-verify the linked source evidence before verifying this module.")
                    else:
                        with conn:
                            conn.execute("UPDATE technology_modules SET review_status=?, reviewer=?, review_note=? WHERE technology_id=?",
                                         (module_review_outcome, module_reviewer.strip() or None, module_review_note.strip() or None, technology_id))
                            audit(conn, "technology_module_reviewed", "technology", technology_id,
                                  {"status": module_review_outcome, "reviewer": module_reviewer.strip(), "note": module_review_note.strip()})
                        st.success("Technology module review recorded.")
                        st.rerun()

        if evidence_rows:
            with st.form("technology_module_form", clear_on_submit=True):
                st.markdown("**Add one module per evidence-backed record**")
                t_evidence_label = st.selectbox("Module evidence", list(evidence_labels), key="technology_evidence")
                a, b = st.columns(2)
                system_name = a.text_input("System family", placeholder="4S, VSS, SafeSite VA pilot")
                module_name = b.text_input("Specific module", placeholder="mobile plant alert, video recording")
                function_raw = st.text_area("Documented function (source-faithful)")
                detection_mode = st.selectbox("Detection mode", ["Passive record", "Tracking", "Sensor threshold", "Rule-based alert", "AI detection", "Human review"])
                deployment_status = st.selectbox("Status", ["Mandated", "Project-selected", "Installed", "Operational", "Optional", "Pilot", "Unknown"])
                project_condition = st.text_input("Project/date condition")
                limitations = st.text_area("Limitations / conditions")
                save_module = st.form_submit_button("Save technology module")
                if save_module:
                    try:
                        module = TechnologyModule(
                            technology_id="tech-" + uuid.uuid4().hex[:16],
                            evidence_id=evidence_labels[t_evidence_label], system_name=system_name.strip(),
                            module_name=module_name.strip(), function_raw=function_raw.strip(),
                            detection_mode=detection_mode, deployment_status=deployment_status,
                            project_condition=project_condition.strip(), limitations=limitations.strip(),
                        )
                        values = module.model_dump()
                        with conn:
                            conn.execute("""INSERT INTO technology_modules (technology_id, evidence_id, system_name,
                                module_name, function_raw, detection_mode, deployment_status, project_condition,
                                limitations, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                (values["technology_id"], values["evidence_id"], values["system_name"], values["module_name"],
                                 values["function_raw"], values["detection_mode"], values["deployment_status"],
                                 values["project_condition"], values["limitations"], now_iso()))
                            audit(conn, "technology_module_created", "technology", values["technology_id"],
                                  {"evidence_id": values["evidence_id"], "status": "Unreviewed"})
                        st.success(f"Saved {values['technology_id']} as an unreviewed module record.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not save module: {exc}")

        st.subheader("Technology–hazard coverage matrix")
        mapping_rows = conn.execute("""SELECT m.*, t.system_name, t.module_name, e.page_or_section
            FROM coverage_mappings m JOIN technology_modules t ON t.technology_id=m.technology_id
            JOIN evidence e ON e.evidence_id=m.evidence_id ORDER BY m.hazard_dimension, m.hazard_label_raw""").fetchall()
        if mapping_rows:
            mapping_frame = pd.DataFrame([dict(row) for row in mapping_rows])
            st.dataframe(mapping_frame, use_container_width=True, hide_index=True)
            st.download_button("Download coverage matrix CSV", mapping_frame.to_csv(index=False).encode("utf-8-sig"),
                               "csdis_technology_hazard_coverage.csv", "text/csv")
        else:
            st.info("No coverage mappings recorded. Proposed mappings require a source-backed rationale and human review.")

        technology_options_rows = conn.execute("SELECT technology_id, system_name, module_name FROM technology_modules WHERE review_status='Human-verified' ORDER BY system_name, module_name").fetchall()
        mapping_evidence_rows = [row for row in evidence_rows if row["review_status"] == "Human-verified"]
        if mapping_evidence_rows and technology_options_rows:
            mapping_evidence_labels = {f"{row['evidence_id']} · {row['source_title']} · {row['page_or_section']}": row["evidence_id"] for row in mapping_evidence_rows}
            technology_labels = {f"{row['technology_id']} · {row['system_name']} · {row['module_name']}": row["technology_id"] for row in technology_options_rows}
            with st.form("coverage_mapping_form", clear_on_submit=True):
                st.markdown("**Propose a mapping (saved as Proposed; never auto-approved)**")
                c_evidence_label = st.selectbox("Mapping evidence", list(mapping_evidence_labels))
                c_technology_label = st.selectbox("Technology module", list(technology_labels))
                hazard_dimension = st.selectbox("Hazard taxonomy dimension", ["Accident type", "Agent", "Unsafe action", "Unsafe condition", "Personal factor", "Injury nature", "Body part"])
                hazard_raw = st.text_input("Hazard label as published")
                hazard_normalized = st.text_input("Researcher harmonised label (optional)")
                coverage_class = st.selectbox("Coverage class", ["Direct", "Indirect", "No documented coverage", "Uncertain"])
                rationale = st.text_area("Evidence-based coding rationale")
                automation_level = st.selectbox("Automation level", ["Passive recording", "Tracking", "Sensor alert", "AI detection", "Manual review"])
                coder = st.text_input("Coder name or initials")
                save_mapping = st.form_submit_button("Save proposed mapping")
                if save_mapping:
                    try:
                        selected_technology_id = technology_labels[c_technology_label]
                        selected_module = conn.execute(
                            "SELECT detection_mode FROM technology_modules WHERE technology_id=?",
                            (selected_technology_id,),
                        ).fetchone()
                        compatible_automation = {
                            "Passive record": {"Passive recording", "Manual review"},
                            "Tracking": {"Tracking", "Manual review"},
                            "Sensor threshold": {"Sensor alert", "Manual review"},
                            "Rule-based alert": {"Sensor alert", "Manual review"},
                            "AI detection": {"AI detection", "Manual review"},
                            "Human review": {"Manual review"},
                        }
                        if selected_module and automation_level not in compatible_automation[selected_module["detection_mode"]]:
                            raise ValueError(
                                f"Automation label {automation_level} conflicts with the module's documented mode "
                                f"({selected_module['detection_mode']}). Passive recording cannot be coded as AI detection."
                            )
                        mapping = CoverageMapping(
                            mapping_id="mapping-" + uuid.uuid4().hex[:16],
                            evidence_id=mapping_evidence_labels[c_evidence_label],
                            technology_id=selected_technology_id,
                            hazard_dimension=hazard_dimension, hazard_label_raw=hazard_raw.strip(),
                            hazard_label_harmonised=hazard_normalized.strip(), coverage_class=coverage_class,
                            coverage_rationale=rationale.strip(), automation_level=automation_level,
                            coder=coder.strip(),
                        )
                        values = mapping.model_dump()
                        with conn:
                            conn.execute("""INSERT INTO coverage_mappings (mapping_id, evidence_id, technology_id,
                                hazard_dimension, hazard_label_raw, hazard_label_harmonised, coverage_class,
                                coverage_rationale, automation_level, coder, coder_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Proposed')""",
                                (values["mapping_id"], values["evidence_id"], values["technology_id"],
                                 values["hazard_dimension"], values["hazard_label_raw"],
                                 values["hazard_label_harmonised"], values["coverage_class"],
                                 values["coverage_rationale"], values["automation_level"], values["coder"]))
                            audit(conn, "coverage_mapping_proposed", "mapping", values["mapping_id"],
                                  {"technology_id": values["technology_id"], "evidence_id": values["evidence_id"], "status": "Proposed"})
                        st.success(f"Saved {values['mapping_id']} as Proposed.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not save mapping: {exc}")

        elif not technology_options_rows:
            st.info("Verify a technology module before proposing it in the coverage matrix.")
        elif not mapping_evidence_rows:
            st.info("Human-verify source evidence before using it to propose coverage mappings.")

        open_mappings = conn.execute("SELECT mapping_id, hazard_label_raw, coder_status, coder FROM coverage_mappings WHERE coder_status!='Locked' ORDER BY mapping_id").fetchall()
        if open_mappings:
            st.subheader("Independent coding and adjudication")
            mapping_labels = {f"{row['mapping_id']} · {row['hazard_label_raw']} · {row['coder_status']}": row["mapping_id"] for row in open_mappings}
            selected_mapping_label = st.selectbox("Mapping to review", list(mapping_labels))
            mapping_reviewer = st.text_input("Second coder / adjudicator", key="mapping_reviewer")
            mapping_review_note = st.text_area("Reviewer rationale / disagreement note", key="mapping_review_note")
            selected_mapping = next(row for row in open_mappings if row["mapping_id"] == mapping_labels[selected_mapping_label])
            allowed_transitions = {
                "Proposed": ["Independently coded"],
                "Independently coded": ["Adjudicated"],
                "Adjudicated": ["Locked"],
            }
            next_coder_status = st.selectbox("Review status", allowed_transitions.get(selected_mapping["coder_status"], ["Independently coded"]), key="mapping_review_status")
            if st.button("Save mapping review"):
                if not mapping_reviewer.strip() or not mapping_review_note.strip():
                    st.error("A reviewer and review note are required to advance mapping status.")
                elif next_coder_status == "Independently coded" and mapping_reviewer.strip().casefold() == selected_mapping["coder"].strip().casefold():
                    st.error("The independent coder must differ from the original coder.")
                else:
                    mapping_id = mapping_labels[selected_mapping_label]
                    with conn:
                        conn.execute("UPDATE coverage_mappings SET coder_status=?, reviewer=?, reviewer_notes=?, reviewed_at=? WHERE mapping_id=?",
                                     (next_coder_status, mapping_reviewer.strip(), mapping_review_note.strip(), now_iso(), mapping_id))
                        audit(conn, "coverage_mapping_reviewed", "mapping", mapping_id,
                              {"status": next_coder_status, "reviewer": mapping_reviewer.strip(), "note": mapping_review_note.strip()})
                    st.success("Mapping review recorded; rationale and evidence links remain attached.")
                    st.rerun()

    with literature_tab:
        st.subheader("Literature discovery and screening")
        st.caption("Metadata discovery is not full-text review. Search pages, queries and outcomes are logged; screening decisions remain human-led.")
        with st.form("literature_search_form"):
            search_query = st.text_input("Bibliographic search query", placeholder="construction safety computer vision hazard detection")
            a, b = st.columns(2)
            search_database = a.selectbox("Search database", ["Both", "Crossref", "OpenAlex"])
            page_size = b.number_input("Results per database", min_value=1, max_value=100, value=25, step=1)
            page_number = st.number_input("Result page", min_value=1, max_value=10000, value=1, step=1)
            run_literature_search = st.form_submit_button("Search metadata")
            if run_literature_search:
                if not search_query.strip():
                    st.error("Enter a search query.")
                else:
                    outcomes = []
                    if search_database in {"Both", "Crossref"}:
                        outcomes.append(search_crossref(conn, search_query.strip(), int(page_size), int(page_number)))
                    if search_database in {"Both", "OpenAlex"}:
                        outcomes.append(search_openalex(conn, search_query.strip(), int(page_size), int(page_number)))
                    for outcome in outcomes:
                        if outcome["error"]:
                            st.warning(f"{outcome['database']} search failed and was logged: {outcome['error']}")
                        else:
                            total = outcome.get("total_results")
                            total_text = f" of {total:,}" if total is not None else ""
                            st.success(f"{outcome['database']} page {outcome['page']}: {outcome['count']} results{total_text}; {outcome['added']} records added, {outcome['duplicates']} possible duplicates flagged. Search ID {outcome['query_id']}.")

        literature_rows = conn.execute(
            """SELECT r.*, q.query_text, q.searched_at FROM literature_records r
               JOIN literature_searches q ON q.query_id=r.query_id
               ORDER BY r.imported_at DESC, r.record_id"""
        ).fetchall()
        if literature_rows:
            literature_frame = pd.DataFrame([dict(row) for row in literature_rows])
            st.dataframe(literature_frame, use_container_width=True, hide_index=True)
            st.download_button("Download literature register CSV", literature_frame.to_csv(index=False).encode("utf-8-sig"),
                               "csdis_literature_register.csv", "text/csv")
            bibtex_data = export_bibtex([dict(row) for row in literature_rows]).encode("utf-8")
            ris_data = export_ris([dict(row) for row in literature_rows]).encode("utf-8")
            export_a, export_b = st.columns(2)
            export_a.download_button("Download BibTeX", bibtex_data, "csdis_literature.bib", "application/x-bibtex")
            export_b.download_button("Download RIS", ris_data, "csdis_literature.ris", "application/x-research-info-systems")
            literature_labels = {f"{row['record_id']} · {row['title']} · {row['year'] or 'year unknown'} · {row['database_name']}": row for row in literature_rows}
            selected_lit_label = st.selectbox("Record to screen", list(literature_labels), key="literature_review_item")
            selected_lit = literature_labels[selected_lit_label]
            st.caption(f"DOI: {selected_lit['doi'] or 'not supplied'} · duplicate review: {selected_lit['duplicate_status']} · query: {selected_lit['query_text']}")
            st.markdown("**Linked full text**")
            full_text_rows = conn.execute(
                "SELECT * FROM literature_full_texts WHERE record_id=? ORDER BY added_at DESC",
                (selected_lit["record_id"],),
            ).fetchall()
            if full_text_rows:
                for attachment_index, attachment in enumerate(full_text_rows):
                    st.caption(f"{attachment['original_filename']} · SHA-256 {attachment['sha256']} · {attachment['file_size']:,} bytes")
                    attachment_path = (LITERATURE_FULLTEXT_DIR / attachment["storage_path"]).resolve()
                    if LITERATURE_FULLTEXT_DIR.resolve() in attachment_path.parents and attachment_path.is_file():
                        attachment_bytes = attachment_path.read_bytes()
                        if hashlib.sha256(attachment_bytes).hexdigest() == attachment["sha256"]:
                            st.download_button(f"Download attached full text {attachment_index + 1}",
                                               attachment_bytes, attachment["original_filename"],
                                               attachment["content_type"], key=f"lit_full_text_download_{attachment['file_id']}")
                        else:
                            st.error(f"Checksum mismatch for local attachment {attachment['original_filename']}; download is disabled.")
                    else:
                        st.warning(f"The attachment file is missing from local storage: {attachment['storage_path']}")
            else:
                st.info("No local full-text file is attached to this record.")
            full_text_upload = st.file_uploader("Attach a lawfully obtained full-text file", key=f"lit_full_text_upload_{selected_lit['record_id']}")
            if full_text_upload is not None and st.button("Store full-text attachment", key=f"store_lit_full_text_{selected_lit['record_id']}"):
                try:
                    attachment, created = store_full_text(
                        conn, LITERATURE_FULLTEXT_DIR, selected_lit["record_id"],
                        full_text_upload.name, full_text_upload.getvalue(), full_text_upload.type or None,
                    )
                    st.success(f"{'Stored' if created else 'Already attached'} {attachment['original_filename']} (SHA-256 {attachment['sha256']}).")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not attach full text: {exc}")
            with st.form("literature_screening_form"):
                screening_options = ["Unscreened", "Include", "Exclude", "Maybe", "Full-text pending"]
                screening_status = st.selectbox("Screening decision", screening_options,
                                                index=screening_options.index(selected_lit["screening_status"]))
                full_text_options = ["Metadata only", "OA full text", "User upload", "Unavailable"]
                full_text_status = st.selectbox("Full-text status", full_text_options,
                                                index=full_text_options.index(selected_lit["full_text_status"]))
                duplicate_options = ["No duplicate detected", "Potential DOI duplicate", "Potential near-title duplicate", "Confirmed duplicate", "Distinct record"]
                if selected_lit["duplicate_status"] not in duplicate_options:
                    duplicate_options.append(selected_lit["duplicate_status"])
                duplicate_status = st.selectbox("Duplicate review", duplicate_options,
                                                index=duplicate_options.index(selected_lit["duplicate_status"]))
                reviewer_name = st.text_input("Reviewer", value=selected_lit["reviewer"] or "")
                exclusion_reason = st.text_input("Exclusion reason", value=selected_lit["exclusion_reason"] or "")
                review_note = st.text_area("Screening note", value=selected_lit["review_note"] or "")
                save_lit_review = st.form_submit_button("Save screening decision")
                if save_lit_review:
                    try:
                        review_literature_record(conn, selected_lit["record_id"], screening_status,
                                                 full_text_status, reviewer_name, review_note, exclusion_reason,
                                                 duplicate_status)
                        st.success("Screening decision saved in the audit trail.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Could not save screening decision: {exc}")
        else:
            st.info("No literature records yet. Run a metadata search to start a logged discovery set.")

        search_rows = conn.execute("SELECT * FROM literature_searches ORDER BY searched_at DESC").fetchall()
        if search_rows:
            st.subheader("Search protocol log")
            search_frame = pd.DataFrame([dict(row) for row in search_rows])
            st.dataframe(search_frame, use_container_width=True, hide_index=True)
            st.download_button("Download literature search log CSV", search_frame.to_csv(index=False).encode("utf-8-sig"),
                               "csdis_literature_search_log.csv", "text/csv")

with tab_project_group:
    activity_tab, about_tab = st.tabs(["Audit activity", "Project status and help"])
    with activity_tab:
        st.subheader("Recent audit events")
        events = conn.execute(
            "SELECT occurred_at, actor, action, entity_type, entity_id, details_json FROM audit_events ORDER BY event_id DESC LIMIT 100"
        ).fetchall()
        if events:
            st.dataframe(pd.DataFrame([dict(row) for row in events]), use_container_width=True, hide_index=True)
        else:
            st.info("No recorded activity yet.")

    with about_tab:
        st.subheader("Implementation status")
        st.markdown(
            """
            **Available in this first working increment**
            - Local SQLite database with source, version, evidence, metric, audit and import-error tables.
            - Idempotent import of the supplied source registry with row-level validation errors.
            - Manual source registration and content-hashed, immutable local file uploads.
            - User-triggered public URL fetches with size/time limits and recorded failures.
            - Browse/download stored versions and verify their SHA-256 integrity with an audit event.
            - Download a portable full backup archive containing the database snapshot, raw files and checksum manifest.
            - Audit history for source imports, registrations, file versions and checksum checks.
            - Native-text PDF page extraction into provisional evidence records, human evidence review, manual metric entry, percentage/denominator checks, CSV export and an unresolved discrepancy register.
            - Evidence-linked policy events, technology modules, and coverage mappings with staged second-coder review and a passive-recording/AI mismatch guard.
            - Structured metric creation from reviewed table rows with explicit label/value cell selection and provenance.
            - Paged Crossref/OpenAlex discovery, search protocol logging, duplicate review, human-led screening, and BibTeX/RIS exports.
            - Content-hashed local full-text attachments linked to literature records and included in backup archives.

            **Next planned increment**
            - Crossref cursor-based deep retrieval, combined multi-ledger analysis packages and OCR fallback.
            """
        )
        st.subheader("Back up local research data")
        st.caption("The archive includes a consistent SQLite snapshot, raw sources, attached literature full texts, and a SHA-256 manifest.")
        if st.button("Prepare full backup archive"):
            try:
                backup_bytes, backup_manifest = create_backup_archive(conn, RAW_DIR, LITERATURE_FULLTEXT_DIR)
                st.session_state["csdis_backup_bytes"] = backup_bytes
                st.session_state["csdis_backup_name"] = "csdis_backup_" + backup_manifest["created_at"].replace(":", "-") + ".zip"
                st.session_state["csdis_backup_count"] = len(backup_manifest["files"])
            except Exception as exc:
                st.error(f"Could not prepare backup: {exc}")
        if st.session_state.get("csdis_backup_bytes"):
            st.download_button(
                "Download backup ZIP",
                st.session_state["csdis_backup_bytes"],
                st.session_state["csdis_backup_name"],
                "application/zip",
            )
            st.caption(f"Archive contains {st.session_state['csdis_backup_count']} database/source files.")
        st.caption(f"Database: {DB_PATH}")
