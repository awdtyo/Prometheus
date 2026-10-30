"""Thin HTTP handlers for the investigation workflow."""

import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Query, status
from fastapi.responses import StreamingResponse

from backend.dependencies import InvestigationServiceDep, SettingsDep
from backend.schemas.investigation import (
    HypothesisListResponse,
    InvestigationCreate,
    InvestigationListResponse,
    InvestigationResponse,
    InvestigationStatus,
    ProgressEvent,
    TimelineResponse,
)

router = APIRouter(prefix="/investigations", tags=["investigations"])

_SSE_HEADERS = {
    "Content-Type": "text/event-stream",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _sse_event_name(event: ProgressEvent) -> str:
    if event.status in (InvestigationStatus.FAILED, InvestigationStatus.CANCELLED):
        return "error"
    if event.stage == "completed":
        return "complete"
    return "progress"


@router.post(
    "",
    response_model=InvestigationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start an investigation",
)
def create_investigation(
    payload: InvestigationCreate,
    service: InvestigationServiceDep,
) -> InvestigationResponse:
    """Start an investigation from a scenario using the configured service."""
    return service.create(payload)


@router.get(
    "",
    response_model=InvestigationListResponse,
    summary="List investigations",
)
def list_investigations(
    service: InvestigationServiceDep,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> InvestigationListResponse:
    """Return investigations newest first with opaque cursor pagination."""
    return service.list(limit=limit, cursor=cursor)


@router.get(
    "/{investigation_id}",
    response_model=InvestigationResponse,
    summary="Read an investigation",
)
def get_investigation(
    investigation_id: str,
    service: InvestigationServiceDep,
) -> InvestigationResponse:
    """Return status and summary metadata for one investigation."""
    return service.get(investigation_id)


@router.get(
    "/{investigation_id}/hypotheses",
    response_model=HypothesisListResponse,
    summary="List ranked hypotheses",
)
def list_hypotheses(
    investigation_id: str,
    service: InvestigationServiceDep,
) -> HypothesisListResponse:
    """Return hypotheses ordered from highest to lowest rank."""
    return service.hypotheses(investigation_id)


@router.get(
    "/{investigation_id}/timeline",
    response_model=TimelineResponse,
    summary="Read the reconstructed timeline",
)
def get_timeline(
    investigation_id: str,
    service: InvestigationServiceDep,
) -> TimelineResponse:
    """Return the reconstructed event timeline in chronological order."""
    return service.timeline(investigation_id)


@router.get(
    "/{investigation_id}/events",
    summary="Stream investigation progress over SSE",
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def stream_investigation_events(
    investigation_id: str,
    service: InvestigationServiceDep,
    settings: SettingsDep,
) -> StreamingResponse:
    """Stream progress events as ``text/event-stream`` until completion."""
    service.get(investigation_id)

    async def event_generator() -> AsyncIterator[str]:
        for event in service.stream_progress(investigation_id):
            event_name = _sse_event_name(event)
            yield (
                f"id: {event.progress}\nevent: {event_name}\ndata: {event.model_dump_json()}\n\n"
            )
            if settings.mock_stream_delay_seconds > 0 and event_name == "progress":
                await asyncio.sleep(settings.mock_stream_delay_seconds)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
