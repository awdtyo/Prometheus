"""Centralized RFC 9457 problem responses for the FastAPI layer."""

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.exceptions import (
    AppError,
    BadRequestError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
)
from backend.schemas.problem import ProblemDetail, ValidationIssue

logger = logging.getLogger("backend.errors")

PROBLEM_MEDIA_TYPE = "application/problem+json"
_PROBLEM_TYPE_BASE = "https://mission-autopsy.local/problems"

__all__ = [
    "PROBLEM_MEDIA_TYPE",
    "AppError",
    "BadRequestError",
    "ConflictError",
    "NotFoundError",
    "ServiceUnavailableError",
    "install_exception_handlers",
]


def _problem_response(
    request: Request,
    *,
    status_code: int,
    title: str,
    detail: str,
    code: str,
    errors: list[ValidationIssue] | None = None,
    headers: dict[str, str] | None = None,
    extensions: dict[str, Any] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    problem = ProblemDetail(
        type=f"{_PROBLEM_TYPE_BASE}/{code}",
        title=title,
        status=status_code,
        detail=detail,
        instance=request.url.path,
        code=code,
        request_id=request_id,
        errors=errors,
        **extensions or {},
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json", exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


async def _app_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    if exc.status_code >= HTTPStatus.INTERNAL_SERVER_ERROR:
        logger.error(
            "Application error: %s",
            exc.detail,
            extra={"event": "app_error", "status_code": exc.status_code, "code": exc.code},
        )
    else:
        logger.warning(
            "Client error: %s",
            exc.detail,
            extra={"event": "app_error", "status_code": exc.status_code, "code": exc.code},
        )
    return _problem_response(
        request,
        status_code=exc.status_code,
        title=exc.title,
        detail=exc.detail,
        code=exc.code,
        headers=exc.headers,
        extensions=exc.extensions,
    )


async def _http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    status_code = int(exc.status_code)
    try:
        title = HTTPStatus(status_code).phrase
        code = HTTPStatus(status_code).name.lower()
    except ValueError:
        title = "HTTP Error"
        code = "http_error"
    detail = exc.detail if isinstance(exc.detail, str) else title
    return _problem_response(
        request,
        status_code=status_code,
        title=title,
        detail=detail,
        code=code,
        headers=dict(exc.headers or {}),
    )


async def _validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    issues = [
        ValidationIssue(
            loc=list(error.get("loc", ())),
            msg=str(error.get("msg", "Invalid value.")),
            type=str(error.get("type", "value_error")),
        )
        for error in exc.errors()
    ]
    logger.info(
        "Request validation failed",
        extra={"event": "validation_error", "error_count": len(issues)},
    )
    return _problem_response(
        request,
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        title="Request validation failed",
        detail="One or more request fields are invalid.",
        code="validation_error",
        errors=issues,
    )


async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unhandled exception",
        extra={"event": "unhandled_exception", "path": request.url.path},
    )
    return _problem_response(
        request,
        status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
        title="Internal server error",
        detail="An unexpected error occurred while processing the request.",
        code="internal_error",
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Register the centralized exception-to-problem+json mapping."""
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
