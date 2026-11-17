# Independent Coding Guide: Technology–Hazard Coverage (2025)

Thank you for acting as an independent coder. Your judgements will be compared with a first coder's to measure how reliable the coding is, so **your independence matters more than agreeing with anyone**. There are no trick questions; where the documents are unclear, saying so is a valid answer.

**Time:** about 1–1.5 hours to read the source documents, then about 4–6 hours to code 148 rows. You can split it across sessions.

---

## 1. What you are judging

Hong Kong and Singapore require certain safety technologies on construction sites. For each reported accident category, you will judge **what the official technical requirements say the technology can do about that hazard**.

You are judging **documented capability only**. You are **not** judging:

- whether the technology was actually installed or worked on any site;
- whether it reduced accidents;
- whether it *could* be adapted to do more than the documents say.

If a capability is not written in the source documents, treat it as not documented, even if you know such technology exists.

## 2. Ground rules for independence

1. **Work alone.** Do not discuss cases with the project lead or anyone else until you have returned your completed sheet.
2. **Code from the source documents in `sources/`**, not from memory, the research paper, or the web.
3. **Do not open** the research manuscript or any file named `CSDIS_Coverage_Matrix_2025_DRAFT.csv` or `CSDIS_Coverage_Pilot_DRAFT.csv`. They contain the first coder's answers.
4. When unsure, choose **Uncertain** and explain why. Do not guess what the first coder chose.
5. Do not change a row after you have moved on unless you noticed a factual error. If you do, say so in `coder_notes`.

## 3. What is in this pack

| File | Purpose |
|---|---|
| `guide.md` | This document: the complete rules. |
| `coding_sheet.csv` | 148 rows to code (74 hazard categories × 2 systems). Open in Excel or any spreadsheet tool. |
| `sources/S002_DEVB_All_Appendices_2025.pdf` | **Hazards.** Hong Kong public-works accident classifications for 2025. |
| `sources/S004_DEVB_TCW_3-2023_..._with_July2026_memo.pdf` | **Hong Kong technology (4S).** The circular, its July 2026 update memo, and Annex A, the specification of every 4S component. |
| `sources/S007_MOM_VSS_for_construction_sector.html` | **Singapore technology (VSS).** Open in a web browser. The live page is at <https://www.mom.gov.sg/workplace-safety-and-health/safe-measures/sectoral-level/video-surveillance-system-for-construction-sector>; use the stored copy, as the live page may have changed. |
| `sources/S001_DEVB_Annual_Report_2025_optional.pdf` | Optional background on the 2025 accident figures. |

## 4. Where to read

**Hazards (S002).** Every row in your sheet gives the exact page and table row in `hazard_locator`:

- Appendix H, PDF p.10: accident type
- Appendix L, PDF p.15: agent (the object or substance involved)
- Appendix M, PDF p.16: unsafe action
- Appendix N, PDF p.17: unsafe condition

Read the category label as published. Do not reinterpret it as something narrower or broader.

**Hong Kong 4S (S004).** Read before you start coding:

- PDF pp.1–2: the July 2026 update memo, which added three components;
- PDF pp.3–6: the circular itself, especially paragraphs 7–9 on who must adopt 4S and how components are chosen;
- PDF pp.7–43: Annex A, the specification. The components are listed in clause **5(12), items (a) to (k)**. For each, note what it senses or detects, where, and what alert it gives.

Annex A clause 6 (virtual-reality training) is training, not monitoring. Do not code it as a technology function.

**Singapore VSS (S007).** Read the whole page, especially "What is VSS", "Where are the locations requiring VSS installation?" and "What are the required specifications for VSS?".

## 5. Unit of coding

Each row is **one hazard category × one system** (`HK 4S` or `SG VSS`). Consider **all** of that system's documented functions together, and record the **strongest** class that any function supports, using this order:

> Direct > Indirect > Uncertain > No documented coverage

List every function you relied on in `matched_functions`.

## 6. Coverage classes

| Class | Use when |
|---|---|
| **Direct** | A documented function explicitly senses, detects, tracks or warns about the hazard event itself, or a clearly named precursor of it. |
| **Indirect** | A documented function could help someone observe, supervise or respond to the hazard, but nothing is specified to detect or alert on this hazard specifically. State the condition that must hold, for example "only if it happens within camera view". |
| **No documented coverage** | After reading the full specification for that system, you found no function relevant to this hazard. This means *not documented*, not *impossible*. |
| **Uncertain** | The wording, the scope, or the match between the hazard label and the function is too unclear to choose another class. Say what is unclear. |

**General-purpose cameras are never Direct on their own.** Recording or live-streaming footage is not detection unless the document specifies automated detection of that kind of event.

### Direct scope: Full or Partial

Whenever you choose **Direct**, also record `coverage_scope`:

- **Full:** the function addresses the published category as a whole.
- **Partial:** the function addresses only a named subset of the category: certain locations, certain equipment, certain groups of workers, or a specific precursor.

*Neutral example (not from this dataset):* a noise sensor specified only at a batching plant gives **Direct, Partial** coverage of "noise exposure", because noise elsewhere on site is not covered.

Leave `coverage_scope` blank for any class other than Direct.

## 7. Decision rules

**Rule A – Paperwork checks are Indirect.** A function that only checks records (a certificate is valid, an inspection is not overdue, a permit has not expired) supports supervision but does not detect the physical hazard or the unsafe act. Code it as **Indirect** at most.
*Neutral example:* a register that alerts when a harness inspection tag is out of date does not detect a worker failing to wear a harness.

**Rule B – Indirect via cameras requires the hazard to be visible.** Use Indirect through camera recording only if the hazard is the kind of event or condition a camera could plausibly show.
- If the event is not visually observable and no sensing function addresses it, use **No documented coverage**. *Neutral example:* noise-induced hearing damage.
- **4S:** camera-based functions exist only in the components that specify cameras. Note this condition in your rationale.
- **VSS:** cameras are required only at the locations the page lists. Say whether the hazard's usual setting is one of those locations, or whether it would be recorded only if it happened to occur in one.

**Rule C – Open-ended lists are Uncertain for unnamed items.** If a document lists items with "including", "such as" or "not limited to", items that are named count as documented. Items that are *not* named are **Uncertain**, not No documented coverage.

**Rule D – "Other Types" is Uncertain.** Categories labelled "Other Types" cannot be matched to a function. Code them Uncertain, with confidence High.

**Rule E – Do not upgrade the automation.** Code what the document says the function does. A recording system is not AI detection unless the document says it is.

**Rule F – Ignore deployment and policy scope.** Treat every component described in the specification as available when judging capability. Whether a component is mandatory, optional or actually installed is recorded elsewhere, not in your class.

## 8. Field-by-field instructions

Do not edit the first eight columns. Fill in the last seven.

| Column | What to enter | Allowed values |
|---|---|---|
| `coverage_class` | Your class (Sections 5–7) | `Direct`, `Indirect`, `No documented coverage`, `Uncertain` |
| `coverage_scope` | Only if Direct (Section 6) | `Full`, `Partial`, or blank |
| `matched_functions` | Every function you relied on, with its clause or location | 4S: clause references such as `5(12)(x)`; VSS: the location or specification line, e.g. `VSS location: <text>`; blank if none |
| `automation_level` | Automation of the **strongest** matched function | `Passive recording`, `Tracking`, `Sensor alert`, `AI detection`, `Manual review`; blank if no function matched |
| `coverage_rationale` | One or two sentences: why this class, and any condition | Free text (**required**) |
| `coder_confidence` | How sure you are | `High`, `Medium`, `Low` |
| `coder_notes` | Anything that did not fit the rules, unclear wording, or a suggested rule change | Free text (optional) |

**Automation levels:**
- **Passive recording:** captures images or video for later viewing.
- **Tracking:** records the status or location of equipment, people or permits.
- **Sensor alert:** a sensor reading or threshold triggers a warning.
- **AI detection:** software automatically recognises a specified event in images or video.
- **Manual review:** a person must inspect or decide; nothing is automated.

Please spell the allowed values exactly as shown. A comparison script reads them.

## 9. Step by step

1. Read Sections 1–8 of this guide.
2. Read the source documents as described in Section 4. Keep notes on what each 4S component and the VSS page actually specify.
3. **Calibration (about 20 minutes).** Code the three practice items in Section 10 on paper, then discuss them with the project lead. They are *not* in your sheet and do not count towards agreement. This is the **only** discussion allowed before you finish.
4. Code all 148 rows. Work dimension by dimension, and check each hazard's page in S002 when the label is unclear.
5. Check that every row has a class, a rationale and a confidence, and that Direct rows have a scope.
6. Save the sheet as `coding_sheet_<your initials>.csv` (keep CSV format) and return it to the project lead.

## 10. Calibration items (practice only)

Code each of these for **both** systems, exactly as you would a sheet row:

1. **Noise-induced hearing loss** among workers near breakers and saws.
2. **Collision between two site vehicles**, with no pedestrian involved.
3. **A worker collapses from a medical event while working alone** in a remote part of the site.

## 11. Common questions

- **The label covers several different situations.** Code the category as published. If a function covers only some of those situations, the answer is Direct, Partial (or Indirect), not Full.
- **Two functions point in different directions.** Record the strongest class (Section 5) and list both functions.
- **A function is described in one clause and its alert in another.** Cite both clauses.
- **I know a product on the market can do this.** It does not count unless the source document specifies it (Section 1).
- **The hazard is reported as zero cases in 2025.** Code it anyway. Some rows have a count of 0, and capability does not depend on frequency.
- **I disagree with a rule.** Apply it anyway and explain your disagreement in `coder_notes`. Rule improvements come from these notes.

## 12. Privacy and use

The source documents are public government publications, provided here only for this coding task; please do not redistribute them. Your coding sheet will be used for research on policy design. Your name or initials will be recorded with your judgements in the project's audit records, and may be acknowledged in any resulting publication if you agree.
