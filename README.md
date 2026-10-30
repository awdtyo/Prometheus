# Mission Autopsy

**AI-assisted spacecraft incident investigation.** Mission Autopsy reconstructs
the most plausible sequence of events behind a mission failure using telemetry,
event logs, subsystem dependencies, temporal relationships, and competing
AI-generated hypotheses.

> **Status: scaffold.** The repository is intentionally runnable, but the domain
> pipeline and investigation UI are not implemented. The backend exposes
> `GET /api/health`; the frontend renders a status shell and proves the HTTP
> connection works.

## Stack

| Layer | Tools |
| --- | --- |
| Domain | Python 3.11+, Pydantic v2, pandas, NumPy, NetworkX, PyYAML, pytest |
| Backend | FastAPI, Uvicorn, SQLite (standard-library `sqlite3`, no ORM yet) |
| Frontend | React 19, Vite 8, TypeScript, oxlint |
| Tooling | Ruff, mypy, pytest-cov, setuptools editable install |

## Repository layout

```text
.
├── autopsy/                 # Pure Python domain package (no FastAPI, no SQLite)
│   ├── models/              # Pydantic domain models
│   ├── ingest/              # Telemetry, event-log, and YAML loaders
│   ├── graph/               # NetworkX causal and temporal graphs
│   ├── simulation/          # Scenario replay and counterfactuals
│   ├── agents/              # Competing hypothesis generation
│   └── analysis/            # Evidence scoring and hypothesis ranking
├── backend/                 # FastAPI application and persistence
│   ├── api/                 # Routers and thin HTTP handlers
│   ├── services/            # Orchestration layer (no FastAPI imports)
│   ├── db/                  # SQLite schema and connection helpers
│   ├── schemas/             # HTTP request/response DTOs
│   ├── settings.py          # Environment-backed configuration
│   └── main.py              # Application factory and entry point
├── frontend/                # React + Vite + TypeScript client
│   └── src/
│       ├── api/             # Typed HTTP client
│       ├── components/      # Presentational components
│       └── types/           # Wire types
├── configs/                 # YAML subsystem and scenario definitions (schemas TBD)
├── fixtures/                # Synthetic telemetry and event-log samples (TBD)
├── docs/                    # Architecture, data contracts, API contract
├── tests/                   # Pytest suite and architecture guard
└── scripts/                 # setup.sh, dev.sh, check.sh
```

## Getting started

### Prerequisites

- Python **3.11+**
- Node.js `^20.19.0` or `>=22.12.0` (required by Vite 8) with npm
- No external database: SQLite is created on first backend startup

### One-command setup

```bash
./scripts/setup.sh
```

The script creates `.venv`, installs the project with development dependencies,
copies `.env.example` to `.env` if needed, and installs the frontend packages.

### Run the stack

```bash
./scripts/dev.sh
```

| Service      | URL                              |
| ------------ | -------------------------------- |
| Frontend     | http://127.0.0.1:5173            |
| Backend API  | http://127.0.0.1:8000            |
| API docs     | http://127.0.0.1:8000/docs       |
| Health check | http://127.0.0.1:8000/api/health |

The Vite dev server proxies `/api` to the backend, so the browser only talks to
the frontend origin during development.

### Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
npm --prefix frontend install
```

Run the backend from the repository root:

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Run the frontend in a second terminal:

```bash
npm --prefix frontend run dev
```

## Configuration

All backend settings use the `MISSION_AUTOPSY_` prefix and are read from the
environment or the repository-root `.env` file. See `.env.example` for every
placeholder.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MISSION_AUTOPSY_ENVIRONMENT` | `development` | `development`, `test`, or `production` |
| `MISSION_AUTOPSY_API_HOST` | `127.0.0.1` | Uvicorn bind host used by scripts |
| `MISSION_AUTOPSY_API_PORT` | `8000` | Uvicorn port used by scripts |
| `MISSION_AUTOPSY_LOG_LEVEL` | `INFO` | Python log level |
| `MISSION_AUTOPSY_DATABASE_PATH` | `./data/mission_autopsy.db` | SQLite file, resolved from the repo root |
| `MISSION_AUTOPSY_CORS_ORIGINS` | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated allowed origins |
| `VITE_API_BASE_URL` | `/api` | Browser-facing API base path |
| `VITE_API_PROXY_TARGET` | `http://127.0.0.1:8000` | Vite dev proxy target |
| `VITE_API_DOCS_URL` | `http://127.0.0.1:8000/docs` | "Open API docs" link |

Vite reads the repository-root `.env` via `envDir`; only `VITE_*` variables are
exposed to browser code. `MISSION_AUTOPSY_LLM_*` values are reserved for the
agent layer and are not read yet. Never commit `.env` or real credentials.

## Checks

Run every check with:

```bash
./scripts/check.sh
```

Or run them individually:

```bash
source .venv/bin/activate
ruff check autopsy backend tests
ruff format --check autopsy backend tests
mypy autopsy backend
pytest

npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

## Architecture rules

1. `autopsy/` is pure Python domain logic. It must not import FastAPI, Starlette,
   the `backend` package, or a database driver. `tests/test_architecture.py`
   enforces this.
2. `backend/` may import `autopsy/`. Routes delegate to `backend.services/`; no
   business logic, graph work, or SQL belongs in route handlers.
3. `backend/services/` orchestrates domain work and persistence. It must not
   import FastAPI.
4. `backend/db/` owns SQLite. It stores records, not domain algorithms.
5. `frontend/` talks to the backend only over HTTP. It must not contain
   simulation, graph, or agent logic.
6. API DTOs (`backend/schemas/`) stay separate from domain models
   (`autopsy/models/`) so the wire contract can evolve independently.
7. YAML in `configs/` is data, validated by Pydantic models in `autopsy/`; it is
   never executable code.

See [`docs/architecture.md`](docs/architecture.md) for the full boundary table
and planned request lifecycle.

## Ownership

| Area | Owner |
| --- | --- |
| `autopsy/` | Developer 1 |
| `backend/` | Developer 2 |
| `frontend/` | Developer 3 |
| `configs/`, `fixtures/` | Shared |
| `docs/`, `tests/`, `scripts/` | Shared |

## What exists today

- Installable `mission-autopsy` package with a framework-independent domain
  skeleton and a `py.typed` marker.
- FastAPI application factory, CORS, settings, health endpoint, and OpenAPI docs.
- SQLite initialization with an `investigations` metadata table.
- React/Vite/TypeScript status shell with a typed health client and Vite proxy.
- Pytest smoke tests, an architecture import guard, Ruff/mypy config, and
  frontend lint/build scripts.

## What does not exist yet

- Telemetry ingestion and validation
- Scenario simulation
- Causal graph algorithms
- Hypothesis-generation agents and ranking
- Investigation persistence workflows
- The investigation UI

The next step is to freeze the contracts in
[`docs/data-contracts.md`](docs/data-contracts.md), then implement `autopsy/`
vertically before adding investigation routes.
