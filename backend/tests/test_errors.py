import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import (
    AppError,
    app_error_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)


class DummyBody(BaseModel):
    name: str
    count: int


@pytest.fixture
def test_app() -> FastAPI:
    app = FastAPI()
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore
    app.add_exception_handler(Exception, generic_exception_handler)  # type: ignore

    @app.get("/custom-error")
    def trigger_custom_error():
        raise AppError(
            code="CUSTOM_CODE",
            message_vi="Thông điệp lỗi mẫu",
            details={"field": "test_field"},
            status_code=400,
        )

    @app.post("/validate")
    def trigger_validation_error(body: DummyBody):
        return {"ok": True}

    return app


def test_app_error_direct():
    err = AppError(
        code="VALIDATION_FAILED",
        message_vi="Prompt không được để trống",
        details={"field": "video_prompt"},
    )
    d = err.to_dict()
    assert d == {
        "error": {
            "code": "VALIDATION_FAILED",
            "message_vi": "Prompt không được để trống",
            "details": {"field": "video_prompt"},
        }
    }


def test_app_error_endpoint(test_app: FastAPI):
    client = TestClient(test_app)
    response = client.get("/custom-error")
    assert response.status_code == 400
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "CUSTOM_CODE"
    assert data["error"]["message_vi"] == "Thông điệp lỗi mẫu"
    assert data["error"]["details"] == {"field": "test_field"}


def test_validation_error_endpoint(test_app: FastAPI):
    client = TestClient(test_app)
    response = client.post("/validate", json={"name": 123})
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_FAILED"
    assert "Dữ liệu yêu cầu không hợp lệ" in data["error"]["message_vi"]
    assert "count" in data["error"]["details"]


def test_not_found_endpoint(test_app: FastAPI):
    client = TestClient(test_app)
    response = client.get("/non-existent-route")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert data["error"]["message_vi"] == "Không tìm thấy tài nguyên"
