# CSDIS Implementation Plan

**Project:** Construction Safety Data Intelligence System (CSDIS)  
**Research use:** Assess alignment between mandated smart construction safety technologies and reported injury hazards in Hong Kong and Singapore.  
**Plan status:** In progress  
**Starting point:** Requirements and seed materials are present. Phase 0 foundations and selected Phase 1 source workflows have been operationally exercised; human review and broader acceptance work remain.

## Product goal

Deliver a local-first research application that keeps source files versioned, ties every extracted value and claim to evidence, supports human review, detects denominator and source conflicts, and produces reproducible research exports. The first usable release focuses on Hong Kong DEVB 2025 data. Later phases add policy mapping, Singapore context, literature workflows and advanced analysis.

## Design rules

- Preserve the original source file and raw value. Corrections apply only to parsed or harmonised fields and are audited.
- Give every source, version, evidence item, metric, policy event and mapping a stable identifier and a source locator where applicable.
- Keep classification dimensions and denominators explicit; never combine counts across dimensions.
- Store conflicting official values side by side. Human review, not recency or arithmetic, decides how a conflict is reported.
- Keep documented capability, policy status, selected modules and observed deployment as distinct fields.
- Treat video recording as passive unless evidence documents automated detection; keep LLM/OCR output provisional until a person reviews it.
- Keep the MVP usable offline after source files are obtained. Network retrieval is optional and must fail clearly without losing the source record.

## Proposed MVP architecture

- **Python 3.12+, Streamlit, SQLite, SQLAlchemy 2, Pydantic v2** for a local analyst application and typed service layer.
- **pandas, pypdf/pdfplumber, openpyxl, python-docx** for tabular work and document ingestion. Use OCR only as an explicitly flagged fallback.
- Organize application code into `csdis/` modules for configuration, persistence/models, source ingestion, extraction, evidence, validation, analysis and exports; keep Streamlit pages as a thin UI layer.
- Store downloaded/uploaded originals under `data/raw/<source_id>/<version_id>/`; store SQLite and generated exports under ignored local-data directories. Do not commit those files or secrets.
- Use deterministic local fixtures/mocked network responses for tests. Do not make test success depend on live government websites.
- Keep API boundaries callable as Python services; defer FastAPI and PostgreSQL until there is a concrete need.

## Phases and exit criteria

### Phase 0 — Repository foundation and integrity model

**Progress:** Initial increment implemented; operational verification remains pending.

**Implemented so far:** package skeleton, dependency list, `.gitignore`, SQLite source/version/evidence/metric/audit schema, Pydantic source contracts, validated idempotent source seed importer, manual source registration, SHA-256 versioned local uploads, bounded public HTTP(S) downloads with per-attempt outcomes, stored-file downloads, audited checksum verification, and portable ZIP backup with database snapshot, raw files, literature attachments and checksum manifest. The Streamlit source/audit dashboard and README are present.

**Work**

1. Establish package layout, dependency/configuration files, `.gitignore`, logging and setup documentation.
2. Define typed schemas and SQLite tables for sources, immutable source versions, evidence, metrics, audit events and review status.
3. Implement source registration, local-file ingestion, SHA-256 checksums, immutable version paths and idempotent re-ingestion.
4. Import `CSDIS_Seed_Source_Registry.csv`; record invalid or incomplete rows as actionable import errors rather than silently dropping them.
5. Create an initial Streamlit shell showing seeded sources, source/version state and recent audit activity.

**Exit criteria**

- A fresh local setup initializes its database and imports the source registry.
- Uploading a file creates a hashed immutable version; registering the same file again does not create duplicate observations.
- Actions that change records produce audit events; original files remain untouched.

### Phase 1 — Hong Kong 2025 extraction and verification (first usable release)

**Progress:** Partial workflow implemented and exercised on the seeded DEVB 2025 report and live rate page; human review and broader acceptance work remain.

**Implemented so far:** Native PDF text extraction creates provisional, page-located evidence records; `pdfplumber` stores candidate table rows with page/table/row locators. The evidence review tab renders the original PDF page beside extracted text or raw table cells. HTML pages create provisional heading/paragraph evidence and candidate table rows, while CSV, XLSX and DOCX tables create candidate rows linked to exact locators. Human review actions preserve the extracted values and record status/reviewer/note in the audit trail. Human-verified rows can be promoted to unverified metrics by explicitly selecting raw label/value cells. Source-specific parsers create provisional DEVB Appendix A and H–O metrics plus separate annual-summary and month-specific rolling-rate metrics from the live page. The official DEVB Annual Report, appendices and live rate page have been retrieved into the local version store. Stored records cover all 10 Appendix A years and extracted H–O table categories; current percentage arithmetic checks report no errors. The 2025 Appendix 4.8 and live-page annual-summary 4.6 remain a high-severity open conflict. The live page also stores each available monthly rolling observation separately; February 2026 is 4.8 and July 2026 is 4.6. Period context is recorded on the conflict, which remains open because the appendix itself labels its 4.8 value as 2025. Researchers can also manually add metrics linked to evidence, review metric status with a required reason for verification decisions, run denominator/percentage checks, automatically flag differing comparable metric values as unresolved conflicts, display each conflict's source versions/snapshot times/locators, export source/evidence/table-row/metric/conflict ledgers to CSV, download a metric CSV manifest with metric IDs, source versions and CSV checksum, export validation findings as JSON, and document human adjudication without overwriting either metric.

**Work**

1. Add PDF upload and optional polite URL retrieval for the DEVB annual report and appendices.
2. Extract text and tables for Appendix A and H–O, retaining source version, page/appendix/table/row locator, raw label/value, units, footnotes and extraction method. Preserve blanks, dashes and qualifiers.
3. Add a review workbench that shows the extracted record and its source locator, and supports accept, edit-parsed-value, reject, ambiguous and discrepancy decisions with reviewer notes.
4. Implement denominator-aware arithmetic checks, missing/zero denominator handling, multi-response warnings, taxonomy separation and source-version change/conflict records.
5. Seed the known 2025 report and appendix facts as fixture data linked to explicit evidence locators; do not treat fixtures as replacements for future source ingestion.
6. Add CSV/XLSX exports with source, denominator, verification state and analysis-manifest information.

**Regression requirements**

- Keep the Annual Report/Appendix A 2025 rate (4.8 per 1,000 workers) and the live DEVB historical page value (4.6) as separate observations with a high-severity unresolved conflict.
- Reproduce Appendix H values 46/189 = 24.34%, 24/189 = 12.70%, and 21/189 = 11.11%.
- Preserve Appendix M 82/222 = 36.94% and Appendix O 129/221 = 58.37%; reject labels that describe either as a share of 189 accidents.
- Keep accident type, agent, unsafe action, unsafe condition and personal factor distinct.

**Exit criteria**

- A researcher can trace each extracted metric to a source version and locator, review it, and export reviewed/provisional status.
- The validation dashboard explains each issue and a safe review action; it does not silently repair source values.

### Phase 2 — Hong Kong policy and technology coverage

**Progress:** Generic evidence-linked policy, technology-module and coverage-mapping workflows are implemented. The DEVB circular/update memo, Buildings Department private-works FAQ, June 2026 Legislative Council reply and Ombudsman DI/464 report are versioned locally. Unreviewed records distinguish public/private scope, dated changes, BWVC passive recording, and non-binding Ombudsman recommendations; no policy or module has been human-adjudicated yet. Coverage mappings now carry separate hazard and technology evidence links (logic in `csdis/coverage.py`); legacy single-link mappings are migrated to `legacy_evidence_id` and blocked from adjudication until both roles are assigned.

**Implemented so far:** UI forms and SQLite tables keep policy event scope separate from module capability/deployment. Coverage mapping stores one taxonomy dimension, source evidence, rationale, automation level, coder and review status. Review transitions proceed Proposed → Independently coded → Adjudicated → Locked, with the second coder required to differ from the original coder. Automation labels are checked against the linked module mode; passive recording cannot be labeled AI detection. The retrieved DEVB PDF begins with a 10 July 2026 update memo followed by the 27 February 2023 circular. Separate unreviewed policy records capture the 2023 public-works requirement, its 2026 scope update, private-works alert conditions effective July 2024 and July 2025, and a 2026 BWVC requirement with no exact start date given in the reply. Unreviewed technology records capture the two BD alert systems as rule-based and BWVCs as passive recording. The reported approximately 60% labelled-project share is stored without invented numerator or denominator counts.

**Work**

1. Review and human-verify the linked DEVB, BD and Legislative Council evidence and unreviewed events; check dates, scope and mandatory wording against source locators.
2. Separate supportive measures (labelling, subsidy, training and enforcement) from mandatory conditions and from observed adoption statistics.
3. Model module selection and exceptions separately; do not promote listed device types to universal installation requirements.
4. Create a module-level technology registry for 4S functions, with documented function, input, output, automation level, status and evidence.
5. Build the four-class coverage matrix (direct, indirect, no documented coverage, uncertain) by one hazard taxonomy dimension per mapping.
6. Add proposed/independently coded/adjudicated review states, rationale, evidence links and reviewer notes.

**Exit criteria**

- 4S requirements do not imply every module is installed at every qualifying project.
- Tool-status tracking is not represented as unsafe hand-tool interaction detection.
- Coverage decisions require evidence and human approval.

### Phase 3 — Singapore context and careful comparison

**Progress:** The seeded Singapore MOM VSS page, 2025 WSH infographic, and November 2026 parliamentary answer are versioned locally. Unreviewed records capture the 1 June 2024 SGD 5 million VSS threshold, its passive-recording specifications, 2024/2025 construction fatal-plus-major injury rates of 31.0 and 26.3 per 100,000 workers, and 2023–2025 public/private injury-report shares. Metrics now have explicit outcome-definition and comparability fields: the DEVB annual-rate pair is marked as comparable candidates with the conflict left open; Singapore construction rates are marked not comparable; public/private shares and the approximate 4S adoption share are context-only, with absent counts retained as validation findings. The SafeSite VA pilot is separately recorded as a pilot, with detection functions left unspecified. DI/464 Tables 1–3 contribute 120 unverified fatal-accident count, type and within-construction share metrics for 2018–2023, explicitly marked context-only; the report’s recommendations on private SSSS adoption and accident review after full adoption are recorded as non-binding recommendations.

**Work**

1. Register MOM VSS requirements, WSH annual statistics and the November 2026 parliamentary answer with versioned evidence.
2. Capture VSS threshold, effective date, zones, image requirements and retention rules.
3. Store the SafeSite Video Analytics pilot as a separate event from baseline VSS.
4. Add metric comparability metadata for outcome definition, cohort, reporting threshold, period and exposure denominator.

**Exit criteria**

- Baseline VSS is described as recording/surveillance; mandatory AI analytics are not inferred.
- Singapore fatal-plus-major injury rates are visibly marked non-equivalent to Hong Kong DEVB public-works reportable accident rates.
- Public/private injury shares are not displayed as project or exposure-adjusted rates.

### Phase 4 — Literature and paper-ready outputs

**Progress:** Crossref/OpenAlex metadata discovery now supports page-number retrieval; every page is logged with query, page, size, total-result count and timestamp. DOI/title duplicate flags, human screening, BibTeX/RIS exports and content-hashed local full-text attachments are implemented. Attached files are included in portable backups. Open-access full-text retrieval and reproducible analysis packages remain pending.

**Implemented so far:** User-triggered paged searches against Crossref and OpenAlex are logged with exact query, database, page number, page size, total-result count, outcome and timestamp. Returned DOI/title near-duplicates remain separate records pending researcher review. Screening, exclusion reasons, full-text status and duplicate adjudication are human-entered and audited. Local full-text uploads are SHA-256 versioned, linked to their metadata record, downloadable from the review UI, and included in the full backup. The literature register exports CSV, BibTeX and RIS while carrying screening and duplicate-review status into reference notes.

**Work**

1. Refine Crossref cursor support for deep result sets; current page-number discovery is adequate for bounded search sets.
2. Keep metadata-only records distinct from full-text reviewed papers; support local uploads and verify the full-text review workflow.
3. Generate reproducible tables, figures, references (BibTeX/RIS), CSV/XLSX packages and a validation report.
4. Include source notes, definitions, denominators, review status and analysis manifest with each output.

**Exit criteria**

- Search and screening decisions are traceable and researcher-led.
- Exported claims and figures have source/evidence lineage and a reproducible manifest.

### Phase 5 — Optional advanced analysis

**Work**

1. Consider monthly-series extraction/digitisation only with explicit provenance and manual verification.
2. Implement an ITS readiness gate checking intervention date, pre/post observations, treated cohort, exposure, stable definitions, adoption/compliance timing and relevant diagnostics.
3. Permit descriptive trends when causal-analysis prerequisites fail; explain the failed prerequisites in the UI/report.
4. Add an optional LLM adapter only if needed, with outputs marked as suggestions that require human review.

**Exit criteria**

- Ineligible ITS analyses are blocked or explicitly marked descriptive-only.
- No causal conclusion is emitted by default; any model reports assumptions and diagnostics.

## Cross-cutting verification checklist

- Implemented pytest regressions cover DEVB monthly/annual rate extraction, repeated-ingest idempotency, period-aware conflict detection, denominator and multiple-response validation, source registration, immutable upload/checksum idempotency, mocked HTTP success/failure/size limits/public redirects/private redirect rejection, CSV/XLSX/DOCX cell preservation, malformed HTML rows, taxonomy separation, and literature full-text hashing/deduplication/screening guards.
- UI smoke checks verified fresh initialization, source registration, evidence review, metric creation, CSV/manifest downloads and backup ZIP generation/download in a disposable app copy. Startup exposed and led to a fix for SQLite connections cached across Streamlit script threads.
- Remaining test gaps include XLSX/DOCX malformed-layout cases, redirect loops/limit behavior, additional URL validation combinations, and multi-response group edge cases.
- The README documents Windows setup/run, data locations, backup/restore, exports and limitations.
- Acceptance claims are limited to features that are implemented and verified; deferred work is listed plainly.

## Immediate next steps

1. Review extracted DEVB, BD, Singapore MOM and Legislative Council evidence in the UI; correct or reject provisional records without silently resolving the 4.8/4.6 conflict.
2. Review DI/464 fatal-accident metrics and recommendations against source pages; keep its industry-wide fatality scope separate from DEVB public-works accident rates.
3. Retrieve remaining relevant sources, including MOM statistical series beyond the one-page infographic, and preserve outcome, cohort and denominator distinctions.
4. Add Crossref cursor-based deep retrieval, richer multi-output analysis packages that combine metrics, conflicts, policy/technology coverage and source manifests; keep screening decisions human-reviewed.
5. Refine missing-denominator and cross-source comparability review, then complete the documented fresh-install and UI acceptance workflow when authorized.

## Risks and decisions to resolve during implementation

- PDF table extraction may be imperfect; retain raw pages and require review for uncertain cells.
- Some seed sources have approximate or evolving page/report details; verify canonical source metadata when ingesting and retain failed retrieval records for manual upload.
- Published totals and percentages may use different bases across appendices; store denominator meaning per metric and do not infer it from neighboring tables.
- Keep the initial app single-user/local. Authentication, shared deployment, PostgreSQL and a separate API are outside the first release unless the research workflow requires them.
