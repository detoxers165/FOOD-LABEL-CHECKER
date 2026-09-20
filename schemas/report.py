from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from schemas.compliance import ComplianceReportModel
from schemas.product import (
    AllergensSchema,
    ContactInformationSchema,
    NutritionSchema,
    ProductSchema,
)


class ReportResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    scan_id: str
    created_at: datetime
    product: ProductSchema | None = None
    nutrition: NutritionSchema | None = None
    ingredients: list[str] = Field(default_factory=list)
    allergens: AllergensSchema | None = None
    contact_information: ContactInformationSchema | None = None
    compliance: ComplianceReportModel


class ReportDocumentInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    scan_id: str
    user_id: Any
    created_at: datetime
    summary: dict[str, Any]
    violations: list[dict[str, Any]]
    passed_checks: list[dict[str, Any]]
    needs_review: list[dict[str, Any]]
    not_applicable: list[dict[str, Any]]
    not_checked: list[dict[str, Any]]
    compliance_engine: dict[str, Any]
