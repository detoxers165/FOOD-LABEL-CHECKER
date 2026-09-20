from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.compliance import ComplianceReportModel
from schemas.product import (
    AllergensSchema,
    ContactInformationSchema,
    NutritionSchema,
    ProductSchema,
)


class ScanErrorModel(BaseModel):
    code: str
    message: str


class ScanImageResponse(BaseModel):
    image_id: str
    original_filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class ScanResultResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    scan_id: str
    status: Literal[
        "uploaded",
        "processing",
        "completed",
        "failed",
    ]
    error: ScanErrorModel | None = None
    created_at: datetime
    updated_at: datetime

    product: ProductSchema | None = None
    ingredients: list[str] = Field(default_factory=list)
    allergens: AllergensSchema | None = None
    nutrition: NutritionSchema | None = None
    contact_information: ContactInformationSchema | None = None
    compliance: ComplianceReportModel | None = None


class ScanListItem(BaseModel):
    scan_id: str
    status: str
    created_at: datetime
    brand: str | None = None
    product_name: str | None = None
    overall_status: str | None = None
    violation_count: int = 0


class ScanListResponse(BaseModel):
    items: list[ScanListItem]
    page: int
    limit: int
    total: int
