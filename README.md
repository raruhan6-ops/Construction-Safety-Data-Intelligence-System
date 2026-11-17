# CSDIS — Construction Safety Data Intelligence System

CSDIS is a local-first research workspace for collecting, versioning and reviewing construction safety sources. The current increment provides a source registry, immutable file storage, evidence extraction/review, denominator-aware metric entry, conflict tracking, policy and coverage registers, and literature metadata discovery/screening.

## Requirements

- Python 3.12 or newer
- The supplied project files, including `CSDIS_Seed_Source_Registry.csv`

## Install and run

From the project folder, on Windows PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

On macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
streamlit run app.py
```

The app creates `data/local/csdis.sqlite3` and imports missing records from the seed source CSV on startup. Register sources or upload source files in the app. Uploaded files are stored under `data/raw/<source_id>/<version_id>/` with the full SHA-256 hash in the database. Re-uploading identical bytes for the same source reuses the existing version. The source registry lets you inspect and download stored versions and run an audited checksum check. A user-triggered HTTP(S) fetch is available for public URLs with a 100 MiB limit, bounded time and redirects, public-address checks, and a recorded success/failure. It does not bypass logins, paywalls or other access controls. PDFs are parsed page by page with native text extraction and candidate table rows; the evidence review tab shows the original PDF page for PDF evidence. HTML creates provisional heading/paragraph evidence and captures a semantic content container when standard text elements omit most of the visible text; HTML tables, CSV, XLSX and DOCX produce candidate rows with source locators. Blank/scanned PDF pages are reported but OCR is not run.

To retrieve selected public sources from the seeded registry, run `python -m csdis.ingest_sources --source-id S001 --source-id S002 --source-id S003`. This stores immutable versions and extracts provisional evidence. The DEVB 2025 report currently contributes Appendix A and H–O metric records; the live DEVB rate table is ingested separately. These values remain unverified. Differing comparable historical rates are recorded as open conflicts for researcher review.

Hong Kong policy sources S004–S006 and S012, and Singapore sources S007–S009, have also been retrieved. Their policy events, technology modules and injury metrics are evidence-linked but unreviewed. DI/464 fatal-accident counts describe the construction industry, not the DEVB public-works reportable-accident series. Singapore public/private injury shares are incident-report breakdowns with missing counts, not project-cohort rates. Singapore construction fatal-plus-major injury rates use a different outcome definition and cohort from the Hong Kong public-works accident-rate series; do not compare them as equivalent outcomes. The SafeSite Video Analytics pilot is tracked separately from the mandatory baseline VSS recording requirement.

Metric records include outcome-definition and comparability fields. Values marked **Comparable candidates** still require source review; **Context only** and **Not comparable** records should not be combined into cross-jurisdiction rates. Missing published incident counts remain visible as validation findings.

## Local data and backup

The database, raw sources and attached literature full texts are local and excluded from Git. In the app's **Project status** tab, prepare and download a full backup ZIP containing a consistent SQLite snapshot, `data/raw/` source files, `data/literature/full_text/` attachments, and a SHA-256 manifest. Keep the archive somewhere separate from the project folder.

To restore, stop the app, keep a copy of the current `data/` directory, then extract the backup ZIP into the project folder so `data/local/csdis.sqlite3`, `data/raw/` and `data/literature/full_text/` are restored in their original locations. Restart the app and use the source version checksum action to check important files. The manifest lists each archived path, size and checksum. Exports will use `data/exports/` as they are implemented.

## Research integrity

Source documents are retained as immutable versions. Extracted page text and table rows are provisional until reviewed. Human-verified table rows can be promoted to unverified metric records by selecting label/value cells; the original row remains linked as evidence. Percentage checks use only the explicitly entered numerator and denominator; they never infer a denominator. Policy, technology and coverage records require evidence links. Literature metadata searches log exact queries and timestamps; DOI/title duplicates are flagged for review and never merged automatically. Local full-text attachments are stored by content hash, linked to their citation record, checksum-verified before download, and included in backups. CSV downloads are available for source, evidence, table-row, metric, conflict, policy, technology, coverage, literature and literature-search registers. The metric CSV has a companion JSON manifest with metric IDs, source versions/snapshot times and the CSV checksum. See `IMPLEMENTATION_PLAN.md` for implementation phases and acceptance criteria.

## Current limitations

- Source uploads are local. Public URL downloads are available when explicitly triggered; automated refresh scheduling is not implemented.
- PDF table extraction is heuristic; candidate rows need review and are not automatically interpreted as metrics. Appendix A and H–O have source-specific provisional parsers; they are not a substitute for human review. CSV/XLSX/DOCX extraction preserves parsed cell values but can differ from displayed spreadsheet formatting. OCR is not implemented.
- Metrics are entered manually or promoted from reviewed table rows. Validation currently checks percentage arithmetic and missing denominator meaning; it does not implement every rule in the specification.
- Literature discovery supports logged page-number searches in Crossref and OpenAlex; Crossref cursor-based deep retrieval is pending. CSV, BibTeX and RIS exports and content-hashed local full-text attachments are available. Open-access full-text retrieval, combined multi-ledger analysis packages and causal-analysis readiness gates are pending. Metric CSVs include a JSON source-version/checksum manifest, and current validation findings can be downloaded as JSON.
- A fresh-install end-to-end workflow has not been verified. Source retrieval and extraction were run against the seeded DEVB sources; all extracted metrics remain unverified.

## Tests

Install the development requirements and run the local regression suite:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The tests cover DEVB monthly and annual rate extraction, repeated-ingest idempotency, period-aware conflict detection, percentage denominator validation and multiple-response warnings, source registration and immutable uploads/checksums, mocked HTTP success/failure/size limits/public redirects/private redirect rejection, CSV/XLSX/DOCX raw-cell preservation, malformed HTML rows, taxonomy separation, and literature full-text hashing/deduplication/screening guards. They use temporary SQLite databases and local fixtures; they do not contact external sites.
