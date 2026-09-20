from typing import Any

from fastapi.responses import JSONResponse


def success_response(
    data: Any,
    *,
    status_code: int = 200,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
        },
    )


def error_response(
    code: str,
    message: str,
    *,
    status_code: int,
    details: Any | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
    }

    if details is not None:
        error["details"] = details

    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": error,
        },
    )
