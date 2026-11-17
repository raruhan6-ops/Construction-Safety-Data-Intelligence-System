# CSDIS Technology?Hazard Coverage Codebook v1.0 (Draft)

**Status:** Draft for pilot; AI-assisted coding, no human validation completed. Do not cite draft classifications as reviewed findings.

## Purpose and unit

Code each **technology module ? hazard label ? jurisdiction/policy scope** combination as one record. A module may have several hazard records; do not infer whole-system coverage from one module. Keep accident frequency (what the injury table reports) separate from technology capability (what the specification says).

## Coverage classes

- **Direct:** The source explicitly describes a module sensing, detecting, tracking, or warning about the named hazard or a precisely equivalent event. A general-purpose camera is not direct detection.
- **Indirect:** The documented function can support observation, supervision, or response to the hazard, but the source does not specify hazard-specific detection/alerting. State the condition (e.g., event is visible in the camera's field of view).
- **No documented coverage:** Use only after the defined source set has been reviewed for that module and hazard. Means no supporting function was documented in that bounded set; it does not prove the technology cannot address the hazard.
- **Uncertain:** The source wording, scope, hazard equivalence, or evidence is insufficient to choose another class. State the unresolved issue.

## Automation level

Code the documented function, not an assumed capability: **Passive recording**, **Tracking**, **Sensor alert**, **AI detection**, or **Manual review**. Do not upgrade a video recording system to AI detection without explicit source evidence. A warning system can be Sensor alert even if its internal logic is rule-based.

## Additional fields and guardrails

- Preserve the source's exact hazard phrase in `hazard_label_raw`; use harmonised labels only for transparent synonyms.
- Keep policy mandate, eligibility, actual installation, operation, and effectiveness as distinct variables. ?Mandated? is not evidence of universal deployment or compliance.
- Preserve source, version, page/section and exact excerpt for both the hazard description and technology function. The current CSDIS mapping table has only one `evidence_id`; this pilot CSV records **both** and exposes a schema limitation to resolve before system import.
- A single source may support multiple labels, but do not double-count category percentages or treat correlated records as independent.
- Do not join national/year-level accident counts to module deployment to make causal or effectiveness claims without project-level exposure and treatment data.
- Keep the 2025 accident-rate discrepancy (4.8 vs 4.6) open; it is outside this module coverage pilot.

## Pilot procedure

1. Two human coders independently code the same pilot rows from the original source artifacts, not only from these excerpts.
2. Each coder records class, automation level, rationale, source locations, and uncertainty before discussion.
3. Compare raw agreement and class-specific disagreements; report the denominator and do not present a reliability statistic from this tiny pilot as stable.
4. Resolve differences with a written rule or retain Uncertain; log adjudicator, date, and rationale.
5. Only then mark source evidence Human-verified and promote mappings through the app workflow. Keep AI draft rows Proposed until that review is complete.

## Pilot scope

Three draft mappings are included: mobile plant danger-zone warning, tower-crane moving-load danger-zone warning, and whether passive BWVC recording directly detects same-level slips/trips/falls. The first two are narrowly direct capability matches; neither establishes effectiveness or project-wide deployment. The third is Uncertain because the documented recording function does not establish continuous hazard-specific detection or relevant camera field of view.
