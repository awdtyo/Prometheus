# Mission Autopsy Backend

FastAPI service for Mission Autopsy. It owns HTTP validation, configuration,
structured logging, error handling, SQLite persistence, and the API contract. It
does not implement simulator, graph, or agent logic. Those belong to the
independent `autopsy/` package and will be connected through a service adapter.

## Architecture

```text
backend/
├── main.py                 # Application factory, lifespan, middleware wiring
├── settings.py             # MISSION_AUTOPSY_* environment configuration
├── dependencies.py         # Shared FastAPI dependencies
├── exceptions.py           # Framework-independent AppError hierarchy
├── errors.py               # RFC 9457 exception handlers
├── logging_config.py       # JSON/text structured logging and request IDs
├── middleware.py           # Access logging and X-Request-ID correlation
├── timeutils.py            # UTC ISO 8601 helpers
├── version.py              # Works with or without the autopsy package
├── api/
│   ├── router.py           # /api and versioned /api/v1 mounting
│   └── routes/             # Thin handlers: health, investigations, catalog
├── schemas/                # Pydantic request/response DTOs
├── services/
│   ├── interfaces.py       # InvestigationService protocol
│   ├── mock_service.py     # Deterministic mock implementation
│   └── factory.py          # Single switch point for the real adapter
└── db/
    ├── database.py         # SQLite connections, schema, migrations
    └── investigations.py   # Investigation queries and keyset pagination
```

Routes validate input and call one service method. Services orchestrate use cases
and persistence. Routes never execute SQL, and services never import FastAPI.

## Local setup

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
cp .env.example .env                 # Windows: Copy-Item .env.example .env
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

The backend creates `data/mission_autopsy.db` on startup. The default mock
services need no `autopsy/` imports or external services.

Useful URLs:

| Endpoint | URL |
| --- | --- |
| Health | http://127.0.0.1:8000/api/v1/health |
| Docs | http://127.0.0.1:8000/docs |
| OpenAPI | http://127.0.0.1:8000/openapi.json |
| Scenarios | http://127.0.0.1:8000/api/v1/scenarios |
| Investigations | http://127.0.0.1:8000/api/v1/investigations |

Example:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/investigations \
  -H "Content-Type: application/json" \
  -d '{"scenario_id":"scn_power_undervoltage"}'
```

## Implemented routes

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Liveness and build metadata |
| `POST` | `/api/v1/investigations` | Start an investigation |
| `GET` | `/api/v1/investigations` | List investigations with cursor pagination |
| `GET` | `/api/v1/investigations/{id}` | Read investigation status |
| `GET` | `/api/v1/investigations/{id}/hypotheses` | List ranked hypotheses |
| `GET` | `/api/v1/investigations/{id}/timeline` | Read the reconstructed timeline |
| `GET` | `/api/v1/investigations/{id}/events` | Stream progress over SSE |
| `GET` | `/api/v1/scenarios` | List scenarios |
| `GET` | `/api/v1/subsystems` | List subsystems |

Unversioned aliases under `/api` remain for local development but are hidden
from OpenAPI. See [`../docs/api-contract.md`](../docs/api-contract.md) for the
full wire contract.

## Error handling and logging

Every failure returns `application/problem+json` with `type`, `title`, `status`,
`detail`, `instance`, `code`, `request_id`, and `errors` for validation failures.
`AppError` subclasses in `exceptions.py` (`NotFoundError`, `BadRequestError`,
`ConflictError`, `ServiceUnavailableError`) cover expected failures without
importing FastAPI. Unknown exceptions are logged and mapped to a generic `500`
problem.

Logs are JSON by default so request IDs, methods, paths, status codes, and
durations can be indexed. Set `MISSION_AUTOPSY_LOG_FORMAT=text` for readable
local output. Every response includes `X-Request-ID`; clients may supply their
own.

## Configuration

All settings use the `MISSION_AUTOPSY_` prefix and are read from the environment
or the repository-root `.env` file. See [`../.env.example`](../.env.example).

| Variable | Default |
| --- | --- |
| `MISSION_AUTOPSY_ENVIRONMENT` | `development` |
| `MISSION_AUTOPSY_API_PREFIX` | `/api` |
| `MISSION_AUTOPSY_API_HOST` | `127.0.0.1` |
| `MISSION_AUTOPSY_API_PORT` | `8000` |
| `MISSION_AUTOPSY_LOG_LEVEL` | `INFO` |
| `MISSION_AUTOPSY_LOG_FORMAT` | `json` |
| `MISSION_AUTOPSY_DATABASE_PATH` | `./data/mission_autopsy.db` |
| `MISSION_AUTOPSY_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` |
| `MISSION_AUTOPSY_USE_MOCK_SERVICES` | `true` |
| `MISSION_AUTOPSY_MOCK_STREAM_DELAY_SECONDS` | `0` |

Relative database paths resolve from the repository root.

## Tests

```bash
python -m pytest tests -q
python -m ruff check backend tests
python -m ruff format --check backend tests
```

The `client` fixture in `tests/conftest.py` creates a temporary SQLite database
for every test, so tests never touch `data/`.

## Connecting the real autopsy pipeline

1. Implement an `InvestigationService` adapter in `backend/services/`.
2. Select it in `backend/services/factory.py` when
   `MISSION_AUTOPSY_USE_MOCK_SERVICES=false`.
3. Keep routes unchanged: they only depend on the service protocol.
4. Map domain models to `backend/schemas/` DTOs in the service layer, not in
   routes and not by leaking `autopsy` models into the wire contract.
