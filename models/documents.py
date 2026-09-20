from datetime import datetime
from typing import Any, Literal, TypedDict


ScanStatus = Literal[
    "uploaded",
    "processing",
    "completed",
    "failed",
]

ComplianceStatus = Literal[
    "PASS",
    "FAIL",
    "NEEDS_REVIEW",
    "NOT_APPLICABLE",
    "NOT_CHECKED",
]


class UserDocument(TypedDict, total=False):
    _id: Any
    email: str
    email_verified: bool
    is_active: bool
    display_name: str | None
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class OtpRequestDocument(TypedDict, total=False):
    _id: Any
    email: str
    purpose: str
    otp_hash: str
    attempts: int
    max_attempts: int
    used: bool
    created_at: datetime
    expires_at: datetime
    purge_at: datetime


class SessionDocument(TypedDict, total=False):
    _id: Any
    jti: str
    user_id: Any
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None


class ImageDocument(TypedDict, total=False):
    image_id: str
    type: str
    storage_backend: str
    storage_key: str
    original_filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class ScanDocument(TypedDict, total=False):
    _id: Any
    scan_id: str
    user_id: Any
    status: ScanStatus
    error: dict[str, str] | None
    images: list[ImageDocument]
    product: dict[str, Any]
    ingredients: list[str]
    allergens: dict[str, Any]
    nutrition: dict[str, Any]
    contact_information: dict[str, Any]
    label_declarations: dict[str, Any]
    raw_extraction: dict[str, Any]
    extraction_metadata: dict[str, Any]
    processing: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ReportDocument(TypedDict, total=False):
    _id: Any
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
