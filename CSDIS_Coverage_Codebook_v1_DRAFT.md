# CSDIS Technology–Hazard Coverage Codebook v1.1 (Draft)

**Status:** Draft; AI-assisted coding, no human validation completed. Do not cite draft classifications as reviewed findings.

**Change log:** v1.1 adds decision rules R1–R7, the full 2025 draft matrix ([CSDIS_Coverage_Matrix_2025_DRAFT.csv](CSDIS_Coverage_Matrix_2025_DRAFT.csv)), and records that CSDIS now stores separate hazard and technology evidence links. v1.0 covered a three-row pilot ([CSDIS_Coverage_Pilot_DRAFT.csv](CSDIS_Coverage_Pilot_DRAFT.csv)).

## Purpose and unit

Code each **technology function × hazard label × jurisdiction/policy scope** combination. A module may have several hazard records; do not infer whole-system coverage from one module. Keep accident frequency (what the injury table reports) separate from technology capability (what the specification says).

## Coverage classes

- **Direct:** The source explicitly describes a module sensing, detecting, tracking, or warning about the named hazard or a precisely equivalent event or named precursor. A general-purpose camera is not direct detection.
- **Indirect:** The documented function can support observation, supervision, or response to the hazard, but the source does not specify hazard-specific detection/alerting. State the condition (e.g., event is visible in the camera's field of view).
- **No documented coverage:** Use only after the defined source set has been reviewed for that module and hazard. Means no supporting function was documented in that bounded set; it does not prove the technology cannot address the hazard.
- **Uncertain:** The source wording, scope, hazard equivalence, or evidence is insufficient to choose another class. State the unresolved issue.

## Automation level

Code the documented function, not an assumed capability: **Passive recording**, **Tracking**, **Sensor alert**, **AI detection**, or **Manual review**. Do not upgrade a video recording system to AI detection without explicit source evidence. A warning system can be Sensor alert even if its internal logic is rule-based.

## Decision rules (v1.1)

- **R1 – Unit for the 2025 matrix.** One row per hazard category per system (HK 4S, SG VSS). Record the strongest class among that system's specified functions and list every matching function with its clause.
- **R2 – Direct scope.** Record `coverage_scope` = **Full** when the function addresses the whole published category, or **Partial** when it addresses only a named subset or precursor (e.g., falls from height only via the no-harness scenario). Report Full and Partial separately; never present Partial as category-wide coverage.
- **R3 – Administrative status checks are Indirect.** Certification/maintenance tracking and permit-to-work expiry alerts verify records, not the physical hazard or unsafe act.
- **R4 – Indirect requires visual observability.** For 4S, footage depends on the AI camera module (cl.5(12)(g)) being selected. For VSS, distinguish hazards whose context is a mandated location from hazards recorded only if they happen to occur in one. Hazards not observable on camera (e.g., particle in eye, gas exposure, defective PPE) are No documented coverage unless a sensing function exists.
- **R5 – Non-exhaustive wording is Uncertain.** The 4S AI PPE scenario reads "including safety helmet and safety vest"; other PPE items are Uncertain, not No documented coverage.
- **R6 – Unspecified categories.** "Other Types" rows are Uncertain and excluded from headline coverage shares (report their size).
- **R7 – Policy status.** Every 4S Annex A component is marked "#" (drafter decides inclusion; Circular para 9), so 4S functions are Project-selected, never per-module mandatory. VSS recording is mandatory at listed locations only.

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
