# Architecture

## 1. Purpose

Mission Autopsy is a monorepo with three independently runnable layers:

- a pure Python domain package (`autopsy/`) that ingests evidence, builds causal
  and temporal graphs, simulates scenarios, generates competing hypotheses, and
  ranks them;
- a FastAPI backend (`backend/`) that exposes the domain over HTTP and owns
  SQLite persistence;
- a React/Vite/TypeScript frontend (`frontend/`) that only communicates with the
  backend over HTTP.

The scaffold deliberately contains no simulator, graph algorithm, agent, or
investigation UI. The boundaries below are what the implementation must preserve.

## 2. System context

```text
┌──────────────────────────┐        HTTP / JSON        ┌──────────────────────────┐
│ frontend/                │ ────────────────────────> │ backend/                 │
│ React + Vite + TS        │ <──────────────────────── │ FastAPI                  │
│                          │                           │                          │
│ api/client.ts            │                           │ api/ -> services/        │
│ components/              │                           │          │       │       │
└──────────────────────────┘                           │          ▼       ▼       │
                                                       │      autopsy/  SQLite    │
                                                       └──────────┬───────┬───────┘
                                                                  │       │
                                             configs/*.yaml ──────>│       │
                                             fixtures/*     ──────>│       │
                                                                  ▼       ▼
                                                       pure domain   backend/db/
```

Dependency direction is one-way: `frontend -> backend -> autopsy`. `autopsy`
never imports `backend`, FastAPI, or SQLite. The backend may import the domain;
the domain never knows the backend exists.

## 3. Module boundaries

| Package / directory       | Responsibility                                                                                         | May depend on                                      | Must not depend on                          |
| ------------------------- | ------------------------------------------------------------------------------------------------------ | -------------------------------------------------- | ------------------------------------------- |
| `autopsy/models/`         | Pydantic domain models, enums, units, and validation rules                                              | stdlib, Pydantic                                   | FastAPI, backend, SQLite                    |
| `autopsy/ingest/`         | Read telemetry, event logs, subsystem YAML, and scenario YAML into typed models                         | models, pandas, NumPy, PyYAML                      | FastAPI, backend, SQLite                    |
| `autopsy/graph/`          | Build and query causal/temporal graphs with NetworkX                                                    | models, NetworkX                                   | FastAPI, backend, SQLite                    |
| `autopsy/simulation/`     | Deterministic scenario replay, perturbation, and event injection                                        | models, graph, NumPy, pandas                       | FastAPI, backend, SQLite                    |
| `autopsy/agents/`         | Competing hypothesis generation, provider adapters, structured output parsing                           | models, graph, provider SDKs                       | FastAPI, backend, SQLite                    |
| `autopsy/analysis/`       | Evidence scoring, consistency checks, ranking, narrative assembly                                       | models, graph, simulation outputs                  | FastAPI, backend, SQLite                    |
| `backend/api/`            | HTTP routing, request validation, response serialization                                                | FastAPI, schemas, dependencies, services           | SQL, autopsy internals, business logic      |
| `backend/services/`       | Use-case orchestration, transaction boundaries, domain/persistence translation                          | autopsy, backend.db, backend.schemas (only if needed) | FastAPI                                  |
| `backend/db/`             | SQLite schema, connections, queries, migrations                                                         | stdlib `sqlite3`                                   | FastAPI, autopsy                            |
| `backend/schemas/`        | HTTP request/response DTOs; wire contract                                                               | Pydantic                                           | autopsy (keeps wire contract decoupled)     |
| `backend/settings.py`     | Environment-backed configuration                                                                        | pydantic-settings                                  | domain logic                                |
| `backend/main.py`         | Application factory, middleware, lifespan, router mounting                                              | FastAPI, api, db, settings                         | domain algorithms                           |
| `frontend/src/api/`       | Typed `fetch` wrappers; the only place that talks HTTP                                                  | browser fetch, `src/types`                         | simulation, graph, agent logic              |
| `frontend/src/components/`| Presentational UI                                                                                       | React, `src/types`                                 | direct backend access, business logic       |
| `frontend/src/types/`     | Wire types mirroring `docs/api-contract.md`                                                             | TypeScript                                         | runtime logic                               |
| `configs/`                | Declarative subsystem and scenario data                                                                 | nothing                                            | code, secrets                               |
| `fixtures/`               | Synthetic sample telemetry and event logs                                                               | nothing                                            | real mission data, secrets                  |

## 4. Dependency rules

1. **One-way imports.** `autopsy` has no knowledge of HTTP, React, or SQLite.
   `tests/test_architecture.py` parses every module under `autopsy/` and fails if
   it imports `backend`, `fastapi`, `starlette`, `sqlalchemy`, or `sqlite3`.
2. **Thin routes.** A route handler validates input, calls one service method,
   and returns a DTO. It does not run graph algorithms, build prompts, or execute
   SQL.
3. **Services own orchestration.** A service coordinates ingestion, simulation,
   graph construction, agent calls, analysis, and persistence. It is the only
   layer that knows the full investigation workflow.
4. **Persistence is backend-owned.** The domain returns models; the service maps
   them to records and writes them through `backend/db/`. SQLite never leaks into
   `autopsy`.
5. **Wire models are separate.** `backend/schemas/` defines the public API;
   `autopsy/models/` defines the domain. Mapping between them happens in the
   service layer, not in routes.
6. **Frontend is a client.** It may render, validate input, and call HTTP. It
   must not reimplement simulation, graph, or agent logic.
7. **Configuration is data.** YAML in `configs/` is loaded and validated by
   `autopsy/ingest/`; it is never imported as Python.

## 5. Request lifecycle

### Current: `GET /api/health`

```text
Browser
  -> Vite dev server (/api proxy)
  -> FastAPI router (backend/api/routes/health.py)
  -> Settings dependency (backend/dependencies.py)
  -> HealthResponse DTO
  -> JSON { status, service, version, environment }
```

There is no service or database call on this path; it is a liveness check.

### Planned: create an investigation

```text
POST /api/investigations
  -> route validates InvestigationCreate
  -> InvestigationService.create()
       -> load scenario + subsystem YAML through autopsy.ingest
       -> create investigation record through backend.db
       -> run autopsy pipeline:
            simulation -> graph -> agents -> analysis
       -> persist hypotheses and ranked narrative
  -> route returns InvestigationRead
```

This flow is **not implemented**. It documents where each future concern belongs.

## 6. Persistence boundary

- SQLite file location comes from `MISSION_AUTOPSY_DATABASE_PATH`
  (default `./data/mission_autopsy.db`, resolved from the repository root).
- `backend/db/database.py` owns the connection helper and idempotent schema.
- The scaffold creates one table, `investigations`, with metadata only:
  `id`, `scenario_id`, `status`, `created_at`, `updated_at`.
- Domain payloads (telemetry, graphs, hypotheses) are not stored yet. Their
  schema waits on `docs/data-contracts.md`.
- Migrations are not set up. Add a migration strategy before changing the schema
  in a shared environment.
- `autopsy` never opens a database connection.

## 7. Configuration and fixtures

- Runtime secrets and deployment settings live in `.env` (ignored by git).
  `.env.example` contains placeholders only.
- Subsystem and scenario definitions live in `configs/subsystems/` and
  `configs/scenarios/` as YAML. They are empty until the data contracts are
  agreed.
- Sample telemetry and event logs live in `fixtures/telemetry/` and
  `fixtures/events/`. They must be synthetic or cleared for public use.
- The frontend reads the repository-root `.env` through Vite's `envDir`; only
  `VITE_*` variables reach the browser.

## 8. Testing strategy

| Layer             | Test type                                                              |
| ----------------- | ---------------------------------------------------------------------- |
| `autopsy`         | Unit tests per module; property tests for temporal ordering later      |
| Domain contracts  | Pydantic validation tests and JSON Schema snapshots                     |
| `backend`         | Service tests with in-memory/temp SQLite; route tests with TestClient  |
| Architecture      | Import-boundary test for `autopsy`                                     |
| `frontend`        | Typecheck, oxlint, production build; component tests later             |

API tests use a temporary SQLite database via the `client` fixture in
`tests/conftest.py`; they never touch `data/`.

## 9. Non-goals for this scaffold

- No telemetry parsing, simulation, graph construction, agent calls, or ranking.
- No investigation CRUD, authentication, background jobs, or streaming.
- No frontend investigation dashboard or data visualization.
- No ORM, migration framework, or external database.
- No deployment configuration (containers, CI, hosting).

## 10. Evolution notes

- Freeze `docs/data-contracts.md` before implementing `autopsy/models/`.
- Add `autopsy` tests alongside each new module; keep the architecture guard
  green.
- Add investigation endpoints only after the service layer exists.
- Introduce `/api/v1` (or another explicit versioning scheme) before the first
  external consumer depends on the API.
- If SQLite access grows, consider a repository module per aggregate before
  reaching for an ORM.
