# CSDIS Technology–Hazard Coverage Codebook v1.2

**Status:** Final for release 1.0.0. Double-coded and adjudicated by consensus (see Reliability procedure). All 97 cited evidence records were verified against the saved source pages on 17 Nov 2026. In the CSDIS database the mappings are Adjudicated, not Locked; the `human_action` column of the matrix records the original workflow instruction.

**Change log:**

- **v1.2 (17 Nov 2026)** responds to the first second-coder comparison:
  - R2 adds a tie-break between Full and Partial;
  - R4 replaces the visibility list with a defining-feature test applied identically to both camera systems;
  - R5 now treats unnamed items in open-ended lists as not documented and records them with an `open_list` flag instead of Uncertain;
  - new R8 assigns detected events to the most specific sibling category;
  - new R9 covers labels that may denote the technology's own absence.

  Classes coded under v1.1 are kept for the reliability statistics. v1.2 applies only to adjudication and later coding.
- **v1.1** adds decision rules R1–R7, the full 2025 matrix (then a draft) ([CSDIS_Coverage_Matrix_2025.csv](CSDIS_Coverage_Matrix_2025.csv)), and records that CSDIS now stores separate hazard and technology evidence links. v1.0 covered a three-row pilot ([CSDIS_Coverage_Pilot.csv](CSDIS_Coverage_Pilot.csv)).

## Purpose and unit

Code each **technology function × hazard label × jurisdiction/policy scope** combination. A module may have several hazard records; do not infer whole-system coverage from one module. Keep accident frequency (what the injury table reports) separate from technology capability (what the specification says).

## Coverage classes

- **Direct:** The source explicitly describes a module sensing, detecting, tracking, or warning about the named hazard or a precisely equivalent event or named precursor. A general-purpose camera is not direct detection.
- **Indirect:** The documented function can support observation, supervision, or response to the hazard, but the source does not specify hazard-specific detection/alerting. State the condition (e.g., event is visible in the camera's field of view).
- **No documented coverage:** Use only after the defined source set has been reviewed for that module and hazard. Means no supporting function was documented in that bounded set; it does not prove the technology cannot address the hazard.
- **Uncertain:** The source wording, scope, hazard equivalence, or evidence is insufficient to choose another class. State the unresolved issue.

## Automation level

Code the documented function, not an assumed capability: **Passive recording**, **Tracking**, **Sensor alert**, **AI detection**, or **Manual review**. Do not upgrade a video recording system to AI detection without explicit source evidence. A warning system can be Sensor alert even if its internal logic is rule-based.

## Decision rules (v1.2)

- **R1 – Unit for the 2025 matrix.** One row per hazard category per system (HK 4S, SG VSS). Record the strongest *documented* class among that system's specified functions, in the order Direct > Indirect > Uncertain > No documented coverage, and list every matching function with its clause.
- **R2 – Direct scope.** Record `coverage_scope` = **Full** only when the function's specified scope covers every situation the published label covers. Use **Partial** when the function addresses only a named subset or precursor, or carries any qualifier the label lacks: at height, designated vehicles or plant, defined spaces, listed parameters, or site vehicles only for a label that includes traffic accidents. **When in doubt, choose Partial.** Report Full and Partial separately; never present Partial as category-wide coverage.
- **R3 – Administrative status checks are Indirect.** Certification/maintenance tracking and permit-to-work expiry alerts verify records, not the physical hazard or unsafe act.
- **R4 – Indirect via cameras: the defining-feature test.** Camera recording supports Indirect only if the feature that places a case in the category can be recognised by a person viewing footage, without measurement, testing or close inspection.
  - *Recognisable:* a slip, a fall, a missing guard, visible dust or fume, rain, a dark or glaring work area, an obvious defect in gear or equipment.
  - *Not recognisable:* a particle entering an eye, gas or vapour concentration, a defect that can only be found by inspection or testing, a person's authorisation status, noise.
  - If only some subtypes named in a label are recognisable, code Indirect and name those subtypes in the rationale.
  - **Apply the same visibility verdict to 4S and VSS** for the same label. The systems differ only in where cameras are:
    - 4S: all site areas, if the AI camera module cl.5(12)(g) is selected.
    - VSS: listed locations only. State whether the hazard's usual setting is a listed location.
- **R5 – Open-ended lists.** Items named in a list are documented. Two kinds of item are *not* documented capability:
  - items left unnamed by an open example list inside a scenario, for example PPE "including safety helmet and safety vest";
  - scenarios left unnamed by an open list as a whole: cl.5(12)(g)(ix) reads "including but not limited to the following$", and Circular para 9 allows devices "not limited to those provided in the Annexes".

  For both kinds, record the strongest class the documented functions support, usually Indirect through the cl.5(12)(g)(i) cameras. Do not use Uncertain for open lists: almost every category would qualify, and Uncertain would then outrank the documented Indirect.

  The `open_list` column marks only the first kind: unnamed items inside a named scenario, which are currently eye protectors, gloves, footwear and dress. The second kind applies to every non-Direct 4S row, so it is reported once as a general caveat ("contracts may specify further AI scenarios"), not row by row.
- **R6 – Unspecified categories.** "Other Types" rows are Uncertain and excluded from headline coverage shares (report their size). Other residual categories, such as "Other Machinery", are not automatically Uncertain. They take the strongest class their documented functions support, but never Direct, because their content is not published.
- **R7 – Policy status.** Every 4S Annex A component is marked "#" (drafter decides inclusion; Circular para 9), so 4S functions are Project-selected, never per-module mandatory. VSS recording is mandatory at listed locations only.
- **R8 – Sibling specificity.** A function supports Direct for a category only if the event it detects would be classified under that category, not under a more specific category in the same classification. For example, the no-harness scenario belongs to "Failure To Use Safety Belt/ Harness" and the missing-platform scenario to "Inadequate Working Space/ Platform". Neither makes the umbrella categories "Unsafe Process or Job Methods", "Improper Procedure" or "Adopting Unsafe Position or Posture" Direct.
- **R9 – Labels that may denote the technology's absence.** Where a label could describe the absence of the alerts the system itself provides (e.g. "Lack Of Warning System"), code Uncertain and flag the row for case-level review.

## Bounded source set (2025 matrix)

- Hazards: DEVB All Appendices 2025 (S002), Appendices H (accident type, base 189 accidents), L (agent, base 199 coded records), M (unsafe action, base 222), N (unsafe condition, base 215). Bases differ because several factors can be coded per accident; never express L–N shares as shares of accidents.
- 4S: DEVB TC(W) No. 3/2023 with the 10 July 2026 update memo (S004), Annex A cl.5(12)(a)–(k), reviewed in full. The memo added MEWP monitoring (i), scaffolding putlog monitoring (j) and smart fire/smoke detection (k). Clause 6 (VR training) is training, not monitoring, and is not coded.
- VSS: MOM VSS page (S007, version retrieved 2026-11-16 19:02 UTC).
- Buildings Department private-works mobile-plant and tower-crane alert systems match 4S cl.5(12)(e) functionally; they change policy scope, not capability coding.

## Additional fields and guardrails

- Preserve the source's exact hazard phrase in `hazard_label_raw`; use harmonised labels only for transparent synonyms.
- Keep policy mandate, eligibility, actual installation, operation, and effectiveness as distinct variables. "Mandated" is not evidence of universal deployment or compliance; `deployment_evidence` stays Unknown without project records.
- Preserve source, version, page/section and exact excerpt for both the hazard description and technology function. CSDIS stores these as separate `hazard_evidence_id` and `technology_evidence_id` links.
- A single source may support multiple labels, but do not double-count category percentages or treat correlated records as independent.
- Do not join national/year-level accident counts to module deployment to make causal or effectiveness claims without project-level exposure and treatment data.
- Keep the 2025 accident-rate discrepancy (4.8 vs 4.6) open; it is outside this coverage coding.

## Reliability procedure

1. Two human coders independently code the same rows from the original source artifacts, not only from these excerpts, without seeing the draft classes.
2. Each coder records class, scope, automation level, rationale, source locations, and uncertainty before discussion.
3. Report raw agreement and Cohen's kappa on coverage class with its denominator, plus class-specific disagreements.
4. Resolve differences with a written rule or retain Uncertain; log adjudicator, date, and rationale.
5. Only then mark source evidence Human-verified and promote mappings through the app workflow. Keep AI draft rows Proposed until that review is complete.

### Round 1 (v1.1 rules, returned 17 Nov 2026)

- **Comparison:** coder A, the AI-assisted draft, against coder B, the independent sheet. Coder B's sheet and the adjudication file are kept outside version control because they identify the coder.
- **Agreement on the first version returned:**
  - all 148 rows: 122/148 agree, κ = 0.670;
  - HK 4S: 54/74, κ = 0.570;
  - SG VSS: 68/74, κ = 0.635;
  - scope, where both coded Direct: 24/27.
- **Revised version:** coder B re-saved the sheet with VSS location notes, giving κ = 0.673 overall and 0.651 for VSS. Coder B confirmed on 21 Nov 2026 that the revision was made after seeing the round-1 comparison, so the paper reports the first version only. Coder B also confirmed that the first version was coded from the source documents alone, without access to coder A's coding.
- **Production:** the project lead confirmed that coder B coded the sheet personally (17 Nov 2026). File timestamps show only when the sheet was saved, not how long the coding took. 26 of the 4S rationales use the same sentence and the 4S rows have no notes, so those rows give limited insight into the reasoning.
- **Adjudication:** both coders resolved the disagreements by consensus on 17 Nov 2026, under v1.2. They decided 32 rows: the 29 disagreements and 3 rows affected by the rule changes. They accepted 29 written proposals and overrode 3: Other Machinery became Indirect, and Defective Protective Gear became Indirect for both systems, which led to the amendments of R4 and R6. The record is kept in the local, untracked folder `coder_pack/returns/`.
- **Applied:** the decisions were applied with `tools/apply_adjudication.py`, which changed 15 rows in class or scope. The 2025 accident-type shares for both systems did not change.
- **Changes within the factor dimensions (L–N):**
  - 4S unsafe action: Direct Full 5 → 2, Indirect 61 → 74, Uncertain 53 → 42;
  - 4S unsafe condition: No documented coverage 3 → 0;
  - VSS unsafe condition: No documented coverage 5 → 0;
  - VSS agent: No documented coverage 1 → 0.
- **Row status:** every row now carries `coder_status` Adjudicated (32) or Independently coded (agreed) (116). Mappings stay below Locked until both evidence links are verified in CSDIS.
- **Evidence verification (17 Nov 2026):** coder B compared all 97 cited evidence records with the saved source pages: 74 DEVB appendix rows, 13 4S circular pages and 10 VSS page sections. Coder B confirmed each label, value or excerpt and noted its page and row. The decisions were entered in CSDIS in one batch afterwards, which is why the review timestamps are identical.
- **CSDIS import:** `tools/import_coverage_matrix.py` loaded the 148 rows as Proposed mappings. Each then moved to Independently coded and to Adjudicated. CSDIS uses Adjudicated also for the 116 agreed rows, with the note "Coders agreed; no adjudication needed". `coverage_scope` (Full or Partial) is kept in the mapping rationale, because the database has no scope field. Rows are not yet Locked.
