"""RFC 9457 problem document schemas."""

from pydantic import ConfigDict, Field

from backend.schemas.base import ApiModel


class ValidationIssue(ApiModel):
    """One field-level validation failure."""

    loc: list[str | int] = Field(default_factory=list)
    msg: str
    type: str


class ProblemDetail(ApiModel):
    """Machine-readable error response returned for every API failure."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str | None = None
    code: str
    request_id: str | None = None
    errors: list[ValidationIssue] | None = None
