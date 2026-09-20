from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

COMPLIANCE_STATUSES = {
    "PASS",
    "FAIL",
    "NEEDS_REVIEW",
    "NOT_APPLICABLE",
    "NOT_CHECKED",
}


class ComplianceTraceModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    rule_id: str
    category: str
    title: str
    description: str
    evidence: Any = None
    status: str = "NEEDS_REVIEW"
    severity: str | None = None
    source: str | None = None
    recommendation: str | None = None
    detected_value: Any = None
    expected_value: Any = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> str:
        normalized = str(value).strip().upper()

        if normalized not in COMPLIANCE_STATUSES:
            return "NEEDS_REVIEW"

        return normalized


class PassedCheckModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    rule_id: str
    category: str
    title: str
    description: str
    evidence: Any = None
    status: str = "PASS"


class NeedsReviewModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    rule_id: str
    category: str
    title: str
    description: str
    reason: str
    evidence: Any = None
    status: str = "NEEDS_REVIEW"


class ComplianceInputModel(BaseModel):
    model_config = ConfigDict(extra="allow")

    overall_status: str = "NEEDS_REVIEW"
    violations: list[ComplianceTraceModel] = Field(default_factory=list)
    passed_checks: list[PassedCheckModel] = Field(default_factory=list)
    needs_review: list[NeedsReviewModel] = Field(default_factory=list)
    not_applicable: list[dict[str, Any]] = Field(default_factory=list)
    not_checked: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("overall_status", mode="before")
    @classmethod
    def normalize_overall_status(cls, value: Any) -> str:
        normalized = str(value).strip().upper()

        if normalized not in COMPLIANCE_STATUSES:
            return "NEEDS_REVIEW"

        return normalized


class ComplianceSummaryModel(BaseModel):
    overall_status: str
    total_rules_checked: int
    passed: int
    failed: int
    needs_review: int
    not_applicable: int
    not_checked: int


class ComplianceReportModel(BaseModel):
    overall_status: str
    summary: ComplianceSummaryModel
    violations: list[ComplianceTraceModel]
    passed_checks: list[PassedCheckModel]
    needs_review: list[NeedsReviewModel]
    not_applicable: list[dict[str, Any]]
    not_checked: list[dict[str, Any]]
