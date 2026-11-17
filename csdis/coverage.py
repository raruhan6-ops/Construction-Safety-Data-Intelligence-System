"""Technology-to-hazard coverage mappings with role-specific evidence links.

A mapping makes two separate claims, each needing its own source support:
the hazard is reported (hazard evidence) and the module documents a relevant
function (technology evidence). Neither claim implies deployment or effectiveness.
"""

from __future__ import annotations

import sqlite3

from csdis.database import audit, now_iso
from csdis.schemas import CoverageMapping

# Automation labels that are compatible with each documented module mode.
COMPATIBLE_AUTOMATION: dict[str, set[str]] = {
    "Passive record": {"Passive recording", "Manual review"},
    "Tracking": {"Tracking", "Manual review"},
    "Sensor threshold": {"Sensor alert", "Manual review"},
    "Rule-based alert": {"Sensor alert", "Manual review"},
    "AI detection": {"AI detection", "Manual review"},
    "Human review": {"Manual review"},
}

ALLOWED_TRANSITIONS: dict[str, str] = {
    "Proposed": "Independently coded",
    "Independently coded": "Adjudicated",
    "Adjudicated": "Locked",
}

# Statuses that may only be reached once both evidence roles are linked and verified.
_REQUIRES_COMPLETE_EVIDENCE = {"Adjudicated", "Locked"}


class CoverageError(ValueError):
    """Raised when a coverage mapping action would break a coding rule."""


def _require_verified_evidence(connection: sqlite3.Connection, evidence_id: str, role: str) -> None:
    row = connection.execute("SELECT review_status FROM evidence WHERE evidence_id=?", (evidence_id,)).fetchone()
    if row is None:
        raise CoverageError(f"{role} evidence {evidence_id} does not exist.")
    if row["review_status"] != "Human-verified":
        raise CoverageError(f"{role} evidence {evidence_id} is {row['review_status']}; it must be Human-verified.")


def check_automation_compatible(detection_mode: str, automation_level: str) -> None:
    allowed = COMPATIBLE_AUTOMATION.get(detection_mode)
    if allowed is None:
        raise CoverageError(f"Unknown module detection mode: {detection_mode}.")
    if automation_level not in allowed:
        raise CoverageError(
            f"Automation label {automation_level} conflicts with the module's documented mode "
            f"({detection_mode}). Passive recording cannot be coded as AI detection."
        )


def propose_coverage_mapping(connection: sqlite3.Connection, mapping: CoverageMapping) -> str:
    """Store a new mapping as Proposed after checking evidence, module and automation rules."""
    module = connection.execute(
        "SELECT detection_mode, review_status FROM technology_modules WHERE technology_id=?",
        (mapping.technology_id,),
    ).fetchone()
    if module is None:
        raise CoverageError(f"Technology module {mapping.technology_id} does not exist.")
    if module["review_status"] != "Human-verified":
        raise CoverageError(f"Technology module {mapping.technology_id} must be Human-verified before mapping.")
    check_automation_compatible(module["detection_mode"], mapping.automation_level)
    _require_verified_evidence(connection, mapping.hazard_evidence_id, "Hazard")
    _require_verified_evidence(connection, mapping.technology_evidence_id, "Technology")
    values = mapping.model_dump()
    with connection:
        connection.execute(
            """INSERT INTO coverage_mappings (mapping_id, hazard_evidence_id, technology_evidence_id,
               technology_id, hazard_dimension, hazard_label_raw, hazard_label_harmonised, coverage_class,
               coverage_rationale, automation_level, coder, coder_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Proposed')""",
            (values["mapping_id"], values["hazard_evidence_id"], values["technology_evidence_id"],
             values["technology_id"], values["hazard_dimension"], values["hazard_label_raw"],
             values["hazard_label_harmonised"], values["coverage_class"], values["coverage_rationale"],
             values["automation_level"], values["coder"]),
        )
        audit(connection, "coverage_mapping_proposed", "mapping", values["mapping_id"],
              {"technology_id": values["technology_id"], "hazard_evidence_id": values["hazard_evidence_id"],
               "technology_evidence_id": values["technology_evidence_id"], "status": "Proposed"})
    return values["mapping_id"]


def set_mapping_evidence(
    connection: sqlite3.Connection,
    mapping_id: str,
    hazard_evidence_id: str,
    technology_evidence_id: str,
    actor: str,
    note: str,
) -> None:
    """Assign role-specific evidence (e.g. to a migrated legacy mapping) before it is locked."""
    if not actor.strip() or not note.strip():
        raise CoverageError("A researcher name and note are required to change mapping evidence.")
    row = connection.execute(
        "SELECT coder_status, hazard_evidence_id, technology_evidence_id FROM coverage_mappings WHERE mapping_id=?",
        (mapping_id,),
    ).fetchone()
    if row is None:
        raise CoverageError(f"Mapping {mapping_id} does not exist.")
    if row["coder_status"] == "Locked":
        raise CoverageError("Locked mappings cannot change evidence links.")
    _require_verified_evidence(connection, hazard_evidence_id, "Hazard")
    _require_verified_evidence(connection, technology_evidence_id, "Technology")
    with connection:
        connection.execute(
            "UPDATE coverage_mappings SET hazard_evidence_id=?, technology_evidence_id=? WHERE mapping_id=?",
            (hazard_evidence_id, technology_evidence_id, mapping_id),
        )
        audit(connection, "coverage_mapping_evidence_set", "mapping", mapping_id,
              {"previous": {"hazard_evidence_id": row["hazard_evidence_id"],
                            "technology_evidence_id": row["technology_evidence_id"]},
               "hazard_evidence_id": hazard_evidence_id, "technology_evidence_id": technology_evidence_id,
               "note": note.strip()},
              actor=actor.strip())


def review_coverage_mapping(
    connection: sqlite3.Connection,
    mapping_id: str,
    next_status: str,
    reviewer: str,
    note: str,
) -> None:
    """Advance a mapping one review step, enforcing coder independence and evidence completeness."""
    if not reviewer.strip() or not note.strip():
        raise CoverageError("A reviewer and review note are required to advance mapping status.")
    row = connection.execute(
        "SELECT coder_status, coder, hazard_evidence_id, technology_evidence_id FROM coverage_mappings WHERE mapping_id=?",
        (mapping_id,),
    ).fetchone()
    if row is None:
        raise CoverageError(f"Mapping {mapping_id} does not exist.")
    expected = ALLOWED_TRANSITIONS.get(row["coder_status"])
    if expected != next_status:
        raise CoverageError(f"Cannot move a {row['coder_status']} mapping to {next_status}.")
    if next_status == "Independently coded" and reviewer.strip().casefold() == row["coder"].strip().casefold():
        raise CoverageError("The independent coder must differ from the original coder.")
    if next_status in _REQUIRES_COMPLETE_EVIDENCE:
        if not row["hazard_evidence_id"] or not row["technology_evidence_id"]:
            raise CoverageError("Assign both hazard and technology evidence before adjudicating or locking.")
        _require_verified_evidence(connection, row["hazard_evidence_id"], "Hazard")
        _require_verified_evidence(connection, row["technology_evidence_id"], "Technology")
    with connection:
        connection.execute(
            "UPDATE coverage_mappings SET coder_status=?, reviewer=?, reviewer_notes=?, reviewed_at=? WHERE mapping_id=?",
            (next_status, reviewer.strip(), note.strip(), now_iso(), mapping_id),
        )
        audit(connection, "coverage_mapping_reviewed", "mapping", mapping_id,
              {"status": next_status, "reviewer": reviewer.strip(), "note": note.strip()})
