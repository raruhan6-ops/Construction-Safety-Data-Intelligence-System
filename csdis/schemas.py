"""Validated data contracts for CSDIS records."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class AuthorityTier(StrEnum):
    PRIMARY = "Primary"
    OFFICIAL_GUIDANCE = "Official guidance"
    PEER_REVIEWED = "Peer-reviewed"
    SECONDARY = "Secondary"
    UNKNOWN = "Unknown"


class ReviewStatus(StrEnum):
    UNREVIEWED = "Unreviewed"
    MACHINE_CHECKED = "Machine-checked"
    HUMAN_VERIFIED = "Human-verified"
    REJECTED = "Rejected"
    SUPERSEDED = "Superseded"


class SourceSeed(BaseModel):
    """A source record imported from the supplied CSV seed registry."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="allow")

    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    publisher: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    url: HttpUrl
    format: str = Field(min_length=1)
    authority_tier: str = Field(min_length=1)
    frequency: str = ""
    data_period: str = ""
    seeded_on: date | str | None = None
    expected_data: str = ""
    verification_notes: str = ""

    def normalized_url(self) -> str:
        return str(self.url)


class SourceRecord(BaseModel):
    """Application-level source record."""

    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    publisher: str = Field(min_length=1)
    title: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    canonical_url: str = Field(min_length=1)
    format: str = Field(min_length=1)
    authority_tier: str = Field(min_length=1)
    frequency: str = ""
    data_period: str = ""
    expected_data: str = ""
    verification_notes: str = ""
    publication_date: date | None = None
    created_at: datetime | None = None

    @field_validator("canonical_url")
    @classmethod
    def validate_canonical_url(cls, value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme == "local" and parsed.path:
            return value.strip()
        if parsed.scheme.lower() in {"http", "https"} and parsed.hostname:
            return value.strip()
        raise ValueError("Enter an HTTP(S) URL or a local: reference.")


class EvidenceRecord(BaseModel):
    """Evidence linked to one immutable source version and locator."""

    evidence_id: str = Field(min_length=1)
    source_version_id: str = Field(min_length=1)
    page_or_section: str = Field(min_length=1)
    exact_quote_or_excerpt: str = Field(min_length=1)
    locator_type: str = Field(min_length=1)
    extraction_method: str = Field(min_length=1)
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    reviewer: str | None = None
    confidence: str = "medium"
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyEvent(BaseModel):
    """Evidence-backed mandate or policy event."""

    policy_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    jurisdiction: Literal["Hong Kong", "Singapore"]
    instrument: str = Field(min_length=1)
    announcement_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    project_threshold: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    covered_project_type: str = Field(min_length=1)
    mandatory_status: str = Field(min_length=1)
    requirement_text: str = Field(min_length=1)


class TechnologyModule(BaseModel):
    """Evidence-backed capability/deployment record for one module."""

    technology_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    system_name: str = Field(min_length=1)
    module_name: str = Field(min_length=1)
    function_raw: str = Field(min_length=1)
    detection_mode: Literal["Passive record", "Tracking", "Sensor threshold", "Rule-based alert", "AI detection", "Human review"]
    deployment_status: Literal["Mandated", "Project-selected", "Installed", "Operational", "Optional", "Pilot", "Unknown"]
    project_condition: str = ""
    limitations: str = ""


class CoverageMapping(BaseModel):
    """Researcher-coded mapping from one hazard dimension to one module."""

    mapping_id: str = Field(min_length=1)
    hazard_evidence_id: str = Field(min_length=1)
    technology_evidence_id: str = Field(min_length=1)
    technology_id: str = Field(min_length=1)
    hazard_dimension: Literal["Accident type", "Agent", "Unsafe action", "Unsafe condition", "Personal factor", "Injury nature", "Body part"]
    hazard_label_raw: str = Field(min_length=1)
    hazard_label_harmonised: str = ""
    coverage_class: Literal["Direct", "Indirect", "No documented coverage", "Uncertain"]
    coverage_rationale: str = Field(min_length=1)
    automation_level: Literal["Passive recording", "Tracking", "Sensor alert", "AI detection", "Manual review"]
    coder: str = Field(min_length=1)
