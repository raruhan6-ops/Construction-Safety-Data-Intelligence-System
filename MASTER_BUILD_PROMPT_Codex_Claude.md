# MASTER BUILD PROMPT — Construction Safety Data Intelligence System (CSDIS)

You are the lead software architect and implementation engineer. Build a local-first research application for the research project:

**“Mandated but Mismatched? Assessing the Alignment Between Smart Construction Safety Technologies and Reported Injury Hazards in Hong Kong and Singapore.”**

The goal is not to invent or fabricate data. The goal is to collect source documents, extract their data, preserve provenance, verify every important value, detect contradictions, support researcher-reviewed technology–hazard mapping, run reproducible analyses, and export paper-ready tables/figures/references.

Read `Construction_Safety_Data_Intelligence_System_Framework.docx`, `CSDIS_Seed_Source_Registry.csv`, and `CSDIS_Core_Data_Dictionary.csv` before implementation. Treat them as project requirements. If a design choice is not specified, choose the simplest safe option and document it.

## 1. Non-negotiable research integrity rules

1. **No fabricated values.** Never fill a missing value with an estimate unless the user explicitly creates a derived estimate. Store it separately, label it derived, and show the formula.
2. **Source of truth and provenance.** Every fact, statistic, policy requirement, chart point and generated claim must link to an exact source version and evidence locator (page, appendix, table, paragraph, row, DOI or URL fragment).
3. **Preserve source values.** Store original raw text exactly (including dashes, blanks, footnotes, labels and units) alongside parsed/normalised values. Never overwrite raw source values.
4. **Contradictions remain visible.** If two official sources disagree, create a conflict record. Do not silently select the newest, average them, or delete one. Show the two values, URLs, versions, publication/retrieval dates and possible metric-definition differences.
5. **Denominators are first-class data.** Every percentage/rate must store numerator, denominator, denominator meaning, unit, cohort, time period and formula when available. Do not assume percentages are divided by total accidents.
6. **Keep taxonomies separate.** Accident type, agent, injury nature, body part, unsafe action, unsafe condition and personal factor are distinct dimensions. Do not add or merge their counts. Multi-response dimensions can exceed total accidents.
7. **Capability is not deployment.** “Documented function”, “mandatory requirement”, “selected for a project”, “installed”, “operational”, “captured on camera” and “automatically detected” are different statuses.
8. **Video is not AI.** Passive VSS recording does not prove automated recognition, warning or prevention. A camera may incidentally capture a hazard without having a dedicated detection function.
9. **Human review required.** OCR/LLM-extracted facts and suggested coverage mappings remain provisional until reviewed. An LLM may suggest, never make final evidentiary decisions.
10. **No causal claims by default.** Trend changes are descriptive unless a qualified design and adequate data support causal inference. The app must gate ITS/difference-in-differences and explain unmet assumptions.
11. **No false cross-country equivalence.** Compare Hong Kong and Singapore rate figures only if injury definitions, reporting thresholds, sectors, cohorts, periods and exposure denominators are demonstrably harmonised. Otherwise use separate context panels and a comparability warning.
12. **Audit trail.** Log imports, edits, validation, reviewer decisions, source updates, analysis runs and exports. Preserve previous versions.
13. **Respect access and terms.** Prefer official public downloads and documented APIs. Do not bypass paywalls, logins, robots controls, access restrictions or publisher terms. For restricted literature, store metadata and a link; allow the researcher to upload a legitimately obtained copy.
14. **Privacy by design.** The project uses public policy/statistical materials. Do not ingest identifiable worker footage or create face-recognition/worker-surveillance features. Keep any optional case documents local and access-controlled.

## 2. Known seed facts and mandatory regression tests

These are seed facts from official sources retrieved on 17 November 2026. Build tests around them. Do not treat them as permission to hard-code results into future source versions.

### Hong Kong 2025 report and appendices
- DEVB 2025 Annual Report URL: https://www.devb.gov.hk/filemanager/en/content_32/2025%20Annual%20Report.pdf
- DEVB 2025 appendices URL: https://www.devb.gov.hk/filemanager/en/content_32/All%20Appendices_2025.pdf
- The report states public-works accident rate: 2024 = 5.8 and 2025 = 4.8 accidents per 1,000 workers per year; man-hour rates = 0.16 and 0.13 accidents per 100,000 man-hours; reportable accidents = 237 and 189; man-hours = 146,236,972.7 and 141,836,191.5.
- 2025 data in Appendix A are captured as at 25 March 2026.
- Appendix H (2025): same-level slip/trip/fall = 46 (24.34%); manual handling = 24 (12.70%); hand-tool accident = 21 (11.11%); total accidents = 189. DEVB report explicitly says hand-tool accidents were not related to work monitored by 4S.
- Appendix M (unsafe actions): lapse of attention = 82 (36.94%) out of 222 coded unsafe-action records; total accident count shown separately as 189. Multiple selections were allowed.
- Appendix O (personal factors): carelessness/not concentrate = 129 (58.37%) out of 221 coded personal-factor records; total accident count shown separately as 189. Multiple selections were allowed.
- Appendix L agents: portable power or hand tools = 29 (14.57%) of agent records; floor/ground/stairs/working surface = 38 (19.10%); denominator is not necessarily the 189 accident count because multiple selections are allowed.
- DEVB overall accident-rate page currently displays 2025 = 4.6 in its historical series: https://www.devb.gov.hk/en/publications_and_press_releases/figures_and_statistics/overall_accident_rates/index.html
- **Regression test HK_RATE_CONFLICT_2025:** both 4.8 (Annual Report/Appendix A) and 4.6 (live historical web table) must remain stored, and a high-severity discrepancy must be flagged. Show source snapshot dates and units. A human analyst must adjudicate or report the discrepancy; do not auto-resolve.
- **Regression test HK_MULTISELECT_DENOMINATOR:** percentage 58.37% is 129 / 221 personal-factor records, not 129 / 189 accidents. Percentage 36.94% is 82 / 222 unsafe-action records, not 82 / 189 accidents. The validator must detect and prevent misleading labels.
- **Regression test HK_TAXONOMY_SEPARATION:** the 21 hand-tool accident types, 29 hand-tool agent records and 13 hand-tool unsafe-equipment/action records (where present) are different measures and must never be merged or added.

### Hong Kong policy
- DEVB Technical Circular (Works) No. 3/2023, issued 27 February 2023: https://www.devb.gov.hk/filemanager/technicalcirculars/en/upload/1393/1/C-2023-03-01.pdf
- It requires capital works contracts with estimated contract sum exceeding HK$30m to adopt SSSS/4S, and project teams select suitable devices based on project nature and high-risk activities. Do not imply every listed device is installed on every project.
- Private-building requirements have separate scope and technical arrangements. Seed official FAQ: https://www.bd.gov.hk/en/resources/faq/index_smart_site_safety_system.html
- Official 24 June 2026 update: https://www.info.gov.hk/gia/general/202606/24/P2026062400525p.htm . It discusses the extension of relevant private-project requirements to additional work categories from July 2025. Extract effective dates and scopes separately.

### Singapore policy and statistics
- MOM VSS rule: https://www.mom.gov.sg/workplace-safety-and-health/safe-measures/sectoral-level/video-surveillance-system-for-construction-sector
- From 1 June 2024, worksites with contract value SGD 5m and above must install VSS. Required areas include height work, scaffolding/formwork, excavation/shoring, lifting, industrial trucks, dangerous vehicular areas, loading/unloading and safely installable confined spaces. Specifications include at least 1080p, 12 fps, date/time/camera ID; retention at least 30 days, and at least 180 days after a reportable incident.
- Do not say AI analytics or automatic hazard detection is compulsory under baseline VSS.
- MOM WSH report 2025: https://www.mom.gov.sg/-/media/mom/documents/safety-health/reports-stats/wsh-national-statistics/wsh-report-2025.pdf . Construction fatal+major injury rate 31.0 (2024) and 26.3 (2025) per 100,000 workers. This is not directly comparable to the Hong Kong DEVB all-reportable public-works rate.
- MOM written answer, 3 November 2026: https://www.mom.gov.sg/newsroom/parliament-questions-and-replies/2026/1103-written-answer-to-pq-on-injury-rates-for-public-and-private-construction-projects . Public/private percentages of fatal and major injuries by available developer data: 2023 39%/61%, 2024 43%/57%, 2025 37%/63%. This is not a rate per project or exposure. The answer also describes a SafeSite Video Analytics pilot initiated in 2025 for selected public projects. Store as a separate pilot/policy event, not as part of mandatory VSS.

### Literature discovery infrastructure
- OpenAlex API documentation: https://help.openalex.org/api/
- Crossref REST API documentation: https://www.crossref.org/documentation/retrieve-metadata/rest-api/
- Use both for bibliographic discovery/deduplication. Metadata is not a substitute for reading and screening studies.

## 3. Product outcome

Build a working local-first application named **CSDIS – Construction Safety Data Intelligence System**. The first usable release should support a single research project but use reusable schemas so another jurisdiction/reporting year can be added later.

The app must produce:
- A versioned source library and source register.
- Extracted structured datasets with page/table/row provenance.
- A reviewer workbench for checking values and mappings.
- A validation and discrepancy dashboard.
- A policy timeline and technology capability inventory.
- A researcher-reviewed Technology–Hazard Coverage Matrix.
- Reproducible descriptive/statistical analysis with assumptions displayed.
- Literature-search register and screening workflow.
- Paper-ready Excel/CSV files, charts (PNG/SVG), tables (DOCX/CSV), references (BibTeX/RIS), and a data-validation report.

## 4. Recommended implementation stack

Use a modular monolith first; avoid premature microservices.

- Python 3.12+
- Streamlit UI for the MVP (fast analyst-facing workflow)
- FastAPI only if a clean API is useful for decoupling; otherwise keep service modules callable from Streamlit and design API boundaries clearly.
- Pydantic v2 for schema validation.
- SQLAlchemy 2 + Alembic; SQLite by default, PostgreSQL-compatible schema.
- pandas or Polars for analytical tables; NumPy/SciPy/statsmodels for statistics.
- httpx + tenacity for polite source downloads with retries and caching.
- pypdf/pdfplumber for PDF text; Camelot or pdfplumber table extraction when suitable; openpyxl for Excel; python-docx for Word.
- OCR (Tesseract or equivalent) only as a fallback for scanned pages; every OCR-derived value requires manual confirmation.
- matplotlib/plotly for charts.
- Crossref and OpenAlex adapters for scholarly metadata.
- pytest for unit/integration tests; ruff for linting; mypy or pyright where practical.
- `.env` for optional API configuration; never commit API keys.

Do not require paid APIs for the MVP. Provide an optional LLM adapter interface (OpenAI / Anthropic / local model), but the system must work without an LLM. LLM output is only a suggested extraction/classification requiring review.

## 5. User interface modules

### A. Project dashboard
- Counts: sources discovered/downloaded, versions, parsed files, extracted records, reviewer-verified records, unresolved conflicts, coverage mappings awaiting review, literature records.
- Data-quality status and recent activity.
- “Research readiness” panel showing incomplete prerequisites for each planned analysis.

### B. Source Registry
- Add sources manually by URL or upload a local file.
- Store publisher, title, document type, jurisdiction, authority tier, publication date, data years, source URL, retrieval date, checksum, file path, licence/access notes, and update cadence.
- Download source while respecting rate limits and website conditions.
- Every download creates a new immutable version; never overwrite previous raw files.
- Show changes between source versions (changed text, table rows, value differences).
- Source authority tiers: primary legislation/government statistics; official guidance/agency; peer-reviewed paper; secondary reporting; unverified.

### C. Document Ingestion & Extraction
- Accept PDF, XLSX, CSV, DOCX, HTML URL and JSON.
- Preserve original files under `data/raw/<source_id>/<version_id>/`.
- Extract metadata and page text.
- Detect pages with weak/no text and offer OCR fallback.
- Extract tables with page and bounding-box/table index when available.
- Every extracted row/cell must preserve raw label, raw value, header path, page, table, row and column location.
- Let researcher correct OCR/table boundaries without losing original extraction.
- Support DEVB appendices A–O and multiple annual reports.
- Make extraction idempotent: re-running same version/config must not duplicate observations.

### D. Data Verification Workbench
Show source excerpt/PDF page beside extracted table. For each value show:
- raw cell string;
- parsed value;
- unit;
- period;
- numerator/denominator;
- source locator;
- extraction method;
- validation results;
- reviewer decision.
Actions: accept, edit parsed value (keep raw), reject, mark ambiguous, flag discrepancy, add note. Require a reason for changing a parsed value. Keep all revisions in audit history.

### E. Data Quality & Discrepancy Centre
Run checks and show severity:
- missing required unit/period/denominator;
- percent cannot be recomputed from stored numerator/denominator within stated rounding tolerance;
- totals inconsistent with category totals;
- multiple-response totals exceed total accident count (warning, not necessarily error);
- repeated or duplicate records;
- impossible/invalid years or future observations;
- mixed currency/unit/denominator;
- source value changes between versions;
- cross-source conflict (e.g. 2025 HK rate 4.8 vs 4.6);
- a claim lacks a supporting evidence record;
- mapping uses only umbrella technology name with no module evidence;
- passive video has been labelled as AI detection;
- a metric from one classification dimension has been combined with another.

Every warning should explain the rule, affected records, severity and a safe resolution path. Never silently repair source values.

### F. Policy & Technology Registry
Store policy instruments as versioned events with jurisdiction, exact scope, threshold, currency, effective date, announcement date, covered project types, mandate status, technical requirement, exceptions, source evidence and superseding policy.

Store each actual technology module independently:
- system family (4S, VSS, SafeSite VA pilot, etc.);
- module (mobile plant alert, lifting alert, confined-space gas sensing, PTW, video recording, AI analytics, wearable device, etc.);
- documented function and trigger;
- input sensor/data;
- output (record, track, alert, dashboard, intervention);
- automation level;
- required vs optional vs encouraged vs pilot;
- project-specific selection/deployment evidence;
- limitations and conditions.

Separate policy requirements from product capability and observed implementation.

### G. Technology–Hazard Coverage Matrix
Use distinct hazard taxonomies: accident type, agent, nature of injury, body part, unsafe action, unsafe condition, personal factor. Each mapping row contains one taxonomy dimension and one specific hazard label.

Coverage classes:
1. Direct – documented module explicitly senses, detects, tracks or alerts on the hazard or operational precursor.
2. Indirect – hazard could be incidentally visible/recorded or inferred, but there is no documented dedicated detection/alert function.
3. No documented coverage – reviewed specifications contain no relevant monitoring/detection function.
4. Uncertain – the evidence is insufficient to determine the capability, policy status or project deployment.

Additional fields: module ID, mandatory status, automation level, project/date condition, evidence IDs, rationale, coder, confidence, independent reviewer, adjudication status.

Do not auto-label coverage from text similarity alone. AI can suggest matches but researcher must confirm each mapping. Support two independent coders and disagreement resolution.

### H. Literature Discovery & Screening
- Search Crossref and OpenAlex APIs; allow manual DOI/title/URL additions.
- Save exact query, database, query date, filters, result count and pagination metadata.
- Deduplicate using DOI, then normalized title + year + first author (flag uncertain duplicates).
- Store abstract, authors, year, journal, DOI, publisher URL, OA URL, metadata source, full-text availability.
- Inclusion/exclusion criteria editable by researcher.
- Screening states: unscreened / include / exclude / maybe / full-text pending / included for synthesis.
- Store exclusion reason; separate title/abstract screening from full-text review.
- Never state the literature search is exhaustive unless the recorded protocol, databases, dates, queries and screening are complete.
- Respect copyright: metadata/abstract only where permitted; no circumvention of paywalls.

### I. Analysis & Visualization
Provide pre-defined analyses that can be reproduced from verified data:
1. Annual and monthly accident count/rate trends, with exact metric definition and denominator displayed.
2. Accident-type distributions by year (e.g. DEVB Appendix H).
3. Separate distributions by agent, injury nature, body part, unsafe action, unsafe condition and personal factor.
4. Severity rate versus frequency rate; do not treat them as interchangeable.
5. Before/after descriptive comparison around policy dates.
6. Public/private comparisons only when cohort definitions and exposure denominators are known; otherwise count/share context only.
7. Technology coverage summaries by classification dimension, policy status and automation level.
8. Optional weighted coverage measure only for a single mutually exclusive taxonomy with valid denominator; disclose weighting and sensitivity. Do not aggregate multi-response dimensions into a single percentage.
9. Singapore/Hong Kong side-by-side contextual panels with comparability status. Block pooled rankings if metrics are not harmonized.

### J. ITS / Causal analysis gate
The app may offer segmented time-series analysis only after a pre-analysis checklist passes:
- exact policy effective date;
- enough pre- and post-policy observations (flag annual 2016–2025 as inadequate for a robust segmented model on its own);
- treated cohort clearly identified (the broad public-works series is not necessarily limited to contracts over HK$30m or actual 4S adopters);
- exposure denominator available for each period;
- stable outcome definition/reporting threshold;
- actual adoption/compliance timing known or explicitly unavailable;
- plausible comparison series and pre-trend checks if controlled design used;
- concurrent policy/intervention/COVID and seasonal/confounding review;
- autocorrelation/seasonality and model diagnostics.

If gates fail, label analysis “descriptive trend only” and do not generate causal language. Provide a diagnostic report explaining which assumptions/data are missing. Never auto-write “4S caused accident reduction”.

### K. Reports & Exports
Create exportable deliverables:
- `verified_metrics.csv` and `.xlsx` with raw and normalised values;
- `accident_taxonomy_<jurisdiction>_<year>.csv`;
- `technology_registry.csv`;
- `coverage_matrix.csv`;
- `source_register.csv` and `evidence_ledger.csv`;
- `policy_timeline.csv`;
- literature screening workbook and BibTeX/RIS;
- high-resolution charts with source notes and accessible labels;
- tables for DOCX/paper;
- a data-quality report listing every unresolved issue;
- analysis run manifest (app version, data version IDs, filters, formulas, date/time).

Generated prose must cite evidence IDs and provide a claim-to-source trace. If no verified source supports a statement, the generator must say “evidence not found” or omit the statement.

## 6. Data model — minimum entities

Create normalized database tables (or equivalent models) for:
- `projects`
- `sources`
- `source_versions`
- `documents`
- `document_pages`
- `extraction_runs`
- `extracted_tables`
- `extracted_cells`
- `evidence_items`
- `metrics`
- `metric_observations`
- `taxonomies`
- `hazard_categories`
- `policy_instruments`
- `policy_events`
- `technology_systems`
- `technology_modules`
- `hazard_technology_mappings`
- `literature_searches`
- `literature_records`
- `screening_decisions`
- `validation_rules`
- `validation_results`
- `source_conflicts`
- `analysis_runs`
- `exports`
- `audit_events`
- `reviewer_users` (single-user local mode first; role-based later).

Use UUID or stable IDs. Add created/updated timestamps. Use soft deletion only where appropriate; immutable source versions/evidence cannot be hard-deleted through the UI.

## 7. Required calculation/validation logic

Implement transparent functions with unit tests:
- `calculate_percentage(numerator, denominator)` with zero/missing denominator guards and explicit rounding.
- `calculate_rate(count, exposure, scale)` where exposure could be man-hours or worker-years; never assume the scale.
- `recompute_percentages_for_table()` but do not assume every table denominator is total accidents; denominator type must be selected/parsed explicitly.
- `compare_published_and_recomputed()` with configurable tolerance and clear result.
- `compare_source_versions()` and `detect_source_conflicts()`.
- `validate_taxonomy_dimension_separation()`.
- `check_multi_response_denominator()`.
- `check_cross_country_comparability()`.
- `analysis_readiness_report()` for ITS and other models.

Include calculations in output with the raw inputs and formula. For rounded published percentages, use a documented tolerance such as ±0.1 percentage point, configurable by source/report. Do not use tolerance to hide a genuine mismatch.

## 8. Suggested repository structure

```text
csdis/
  README.md
  pyproject.toml
  .env.example
  .gitignore
  app.py                     # Streamlit entry point
  config/
    settings.py
    source_registry_seed.csv
    taxonomy_seed.yaml
    validation_rules.yaml
  csdis/
    core/                    # config, logging, IDs, hashing, errors
    db/                      # models, migrations, repositories
    sources/                 # downloaders, registry, versioning
    ingestion/               # PDF/Excel/CSV/DOCX/HTML parsers
    extraction/              # tables, cells, page locators, OCR fallback
    evidence/                # evidence objects and citation resolver
    validation/              # arithmetic, semantic, cross-source rules
    policy/                  # timelines, mandates, thresholds
    technology/              # systems, modules, capabilities
    taxonomy/                # accident dimensions / harmonisation
    mapping/                 # coverage coding, adjudication
    literature/              # OpenAlex, Crossref, screening, dedup
    analytics/               # descriptive, trend, ITS eligibility, charts
    exports/                 # CSV/XLSX/DOCX/BibTeX, manifests
    ui/                      # pages and reusable components
  data/
    raw/                     # immutable source downloads; gitignored
    processed/               # intermediate parse outputs; gitignored
    exports/                 # generated user outputs; gitignored by default
    csdis.sqlite             # local DB; gitignored
  tests/
    fixtures/                # synthetic/public test PDFs and spreadsheets
    unit/
    integration/
    regression/
  docs/
    data_dictionary.md
    validation_rules.md
    research_protocol.md
    source_register.md
    architecture.md
```

## 9. API / service boundaries

Even if MVP is Streamlit-first, create clean service functions. If FastAPI is added, include endpoints equivalent to:
- `GET/POST /api/sources`
- `POST /api/sources/{id}/fetch`
- `GET /api/sources/{id}/versions`
- `POST /api/documents/{id}/extract`
- `GET /api/evidence/{id}`
- `GET/POST /api/metrics`
- `POST /api/validation/run`
- `GET /api/validation/issues`
- `GET/POST /api/policies`
- `GET/POST /api/technology-modules`
- `GET/POST /api/coverage-mappings`
- `GET/POST /api/literature/searches`
- `POST /api/analysis/{analysis_type}/run`
- `POST /api/exports/{export_type}`

Validate all inputs with Pydantic. Provide understandable errors. Never expose local file paths or secrets in public API responses.

## 10. MVP implementation phases

### Phase 0 — project skeleton and research integrity (must complete first)
- Initialize repo, environment, config, DB/migrations, logging, tests and docs.
- Implement immutable sources/source versions, SHA-256 hashing, evidence IDs and audit trail.
- Load the source registry seed CSV.

### Phase 1 — Hong Kong DEVB data extraction and verification (first usable milestone)
- Ingest DEVB 2025 report and appendices; support local PDF upload and URL fetch.
- Extract Appendix A, H, I, J, K, L, M, N and O tables with provenance.
- Build data verification workbench and core denominator-aware validations.
- Implement the 4.8 vs 4.6 conflict regression test.
- Implement the 58.37% and 36.94% multi-response denominator tests.
- Export verified data to CSV/XLSX.

### Phase 2 — Hong Kong policy and technology mapping
- Seed DEVB circular, BD FAQ and June 2026 update as versioned policy events.
- Build technology module registry and four-class coverage matrix.
- Add human coding, second reviewer and adjudication flow.

### Phase 3 — Singapore policy/statistical context
- Ingest MOM VSS page and technical guidance/FAQ; extract zones, technical specification and retention.
- Ingest MOM WSH annual statistics and 2026 parliamentary written answer.
- Mark rate definitions/comparability and keep SafeSite Video Analytics pilot separate from mandatory VSS.

### Phase 4 — literature workflow and paper outputs
- Add Crossref/OpenAlex, query logging, deduplication and screening.
- Create paper-ready charts/tables/citations and quality report.

### Phase 5 — optional advanced analysis
- Monthly series extraction/digitisation with explicit manual checks.
- ITS readiness gate and model diagnostics; do not run as causal model until gates pass.
- Optional LLM-assisted extraction/classification, always requiring approval.

## 11. Acceptance criteria

The application is not complete until all of the following pass:

1. A user can add a source by URL or upload a PDF and the file is stored with a hash and immutable version.
2. The same document can be reprocessed without duplicate records.
3. Each extracted table value can be opened beside its exact source page/row.
4. Raw source text is preserved when parsed values are corrected.
5. The application imports the seed source register.
6. The DEVB Appendix A 2025 value 4.8 and the live page 4.6 are both stored with a visible conflict.
7. Appendix H values 46/189 = 24.34%, 24/189 = 12.70%, and 21/189 = 11.11% are reproducible from stored counts and denominators.
8. Appendix M 82/222 = 36.94% is not relabelled as 82/189.
9. Appendix O 129/221 = 58.37% is not relabelled as 129/189.
10. The user can distinguish accident type, agent, unsafe action, unsafe condition and personal factor.
11. The user can distinguish camera recording from automated AI detection.
12. The user can distinguish policy mandated, project-selected, actual installed, operational, optional and pilot statuses.
13. The technology–hazard mapping requires source-backed rationale and human approval.
14. The Singapore national rate is flagged as non-equivalent to the Hong Kong public-works reportable accident rate.
15. The app identifies that the 2026 SafeSite VA pilot is not the same instrument as the 2024 baseline VSS mandate.
16. An ITS report is blocked or marked descriptive-only when cohort/exposure requirements are unmet.
17. Every chart/table export includes source/metric notes and an analysis manifest.
18. Test suite, linting and a fresh-install smoke test pass. README explains setup, run, backup, restore and export.

## 12. Required test cases

Write tests before, or alongside, implementation. Include:
- percentage from integer counts and correct denominator;
- missing/zero denominator handling;
- source conflict not auto-resolved;
- duplicate DOI and near-duplicate title review;
- parser preserving dash, blank and footnote markers;
- multi-response category sums > total accidents as warning, not error;
- taxonomy dimension separation;
- VSS passive recording not misclassified as AI detection;
- project-specific 4S component status not generalized to all contracts;
- time series eligibility fails when treatment cohort is not isolated;
- local source file re-ingestion is idempotent;
- corrupted/unavailable source URL returns a clear error and preserves the source record.

## 13. Build instructions to the coding agent

1. Inspect the working directory and the supplied framework files.
2. Produce a short `IMPLEMENTATION_PLAN.md` and then implement. Do not stop after writing a plan.
3. Start with Phase 0 and Phase 1. Deliver a working app, not only architecture diagrams.
4. Use real official URLs from the seed registry, but make tests deterministic by using local fixtures/mocked HTTP responses. Do not make tests depend on live government websites.
5. If a source website blocks or changes, log the failure and let the user upload the file manually. Do not invent missing data.
6. Use explicit data models and type hints. Write docstrings for calculation and validation functions.
7. Build a polished analyst-friendly UI with clear status labels, filter controls, source preview, validation issues and export buttons.
8. Do not commit downloaded source documents, the local DB, local exports, API keys or private user files. Add `.gitignore`.
9. Write a complete README with installation and operating steps for Windows, macOS and Linux where practical.
10. Run unit tests, integration tests, linting and an end-to-end smoke test. Fix failures before declaring completion.
11. At completion, provide: features implemented, exact setup/run commands, test results, known limitations, and the next highest-priority tasks.
12. Never state that a feature works unless it has been implemented and tested.

**Begin now.**