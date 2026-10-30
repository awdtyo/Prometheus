"""Request-scoped middleware for correlation IDs and access logging."""

import logging
import time
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.logging_config import reset_request_id, set_request_id

logger = logging.getLogger("backend.request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware:
    """Attach a request ID, emit an access log, and time every HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get(REQUEST_ID_HEADER.lower()) or uuid4().hex
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = set_request_id(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = MutableHeaders(scope=message)
                response_headers[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.info(
                "HTTP %s %s -> %s",
                scope.get("method", ""),
                scope.get("path", ""),
                status_code,
                extra={
                    "event": "http_request",
                    "method": scope.get("method", ""),
                    "path": scope.get("path", ""),
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "request_id": request_id,
                },
            )
            reset_request_id(token)
