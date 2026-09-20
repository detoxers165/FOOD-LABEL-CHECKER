from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
    INVALID_EMAIL = "INVALID_EMAIL"
    OTP_SEND_FAILED = "OTP_SEND_FAILED"
    OTP_EXPIRED = "OTP_EXPIRED"
    INVALID_OTP = "INVALID_OTP"
    OTP_TOO_MANY_ATTEMPTS = "OTP_TOO_MANY_ATTEMPTS"
    RATE_LIMITED = "RATE_LIMITED"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    SCAN_NOT_FOUND = "SCAN_NOT_FOUND"
    INVALID_FILE = "INVALID_FILE"
    AI_PROCESSING_FAILED = "AI_PROCESSING_FAILED"
    DATABASE_ERROR = "DATABASE_ERROR"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode | str,
        message: str,
        *,
        status_code: int = 400,
        details: Any | None = None,
    ):
        self.code = str(code)
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(message)


def public_error(
    code: ErrorCode | str,
    message: str,
    *,
    status_code: int,
    details: Any | None = None,
) -> AppError:
    return AppError(
        code=code,
        message=message,
        status_code=status_code,
        details=details,
    )
