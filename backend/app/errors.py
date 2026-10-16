from typing import Any, Optional

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message_vi: str,
        details: Optional[dict[str, Any]] = None,
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ):
        super().__init__(message_vi)
        self.code = code
        self.message_vi = message_vi
        self.details = details or {}
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message_vi": self.message_vi,
                "details": self.details,
            }
        }


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    details: dict[str, Any] = {}
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        details[loc or "body"] = err.get("msg")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_FAILED",
                "message_vi": "Dữ liệu yêu cầu không hợp lệ",
                "details": details,
            }
        },
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR"
    message_vi = "Không tìm thấy tài nguyên" if exc.status_code == 404 else str(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code,
                "message_vi": message_vi,
                "details": {"detail": exc.detail} if isinstance(exc.detail, str) else exc.detail,
            }
        },
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message_vi": "Đã xảy ra lỗi máy chủ nội bộ",
                "details": {"message": str(exc)},
            }
        },
    )
