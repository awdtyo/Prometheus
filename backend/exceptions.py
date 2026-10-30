"""Framework-independent application exceptions.

These classes describe expected failures without importing FastAPI, so services
can raise them while the HTTP layer decides how to serialize them.
"""

from http import HTTPStatus
from typing import Any


class AppError(Exception):
    """Base class for errors that map to a known HTTP problem response."""

    def __init__(
        self,
        detail: str,
        *,
        status_code: int = HTTPStatus.BAD_REQUEST,
        code: str = "bad_request",
        title: str | None = None,
        headers: dict[str, str] | None = None,
        extensions: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = int(status_code)
        self.code = code
        self.title = title or HTTPStatus(self.status_code).phrase
        self.headers = headers
        self.extensions = extensions or {}


class BadRequestError(AppError):
    """The request is syntactically valid but cannot be processed."""

    def __init__(self, detail: str, *, code: str = "bad_request") -> None:
        super().__init__(detail, status_code=HTTPStatus.BAD_REQUEST, code=code)


class NotFoundError(AppError):
    """A requested resource does not exist."""

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            f"{resource} '{identifier}' was not found.",
            status_code=HTTPStatus.NOT_FOUND,
            code="not_found",
            extensions={"resource": resource, "identifier": identifier},
        )


class ConflictError(AppError):
    """The request conflicts with the current resource state."""

    def __init__(self, detail: str, *, code: str = "conflict") -> None:
        super().__init__(detail, status_code=HTTPStatus.CONFLICT, code=code)


class ServiceUnavailableError(AppError):
    """A required service has not been configured or is temporarily unavailable."""

    def __init__(self, detail: str, *, code: str = "service_unavailable") -> None:
        super().__init__(
            detail,
            status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            code=code,
        )
