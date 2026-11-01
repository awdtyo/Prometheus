"""Real investigation service backed by the autopsy pipeline.

Implements ``backend.services.interfaces.InvestigationService``. In real mode
(``MISSION_AUTOPSY_USE_MOCK_SERVICES=false``) every investigation/run executes
``autopsy.pipeline.run_scenario`` in a worker thread through the job queue,
bridges pipeline progress callbacks into the SSE stream thread-safely, and
persists the resulting ``RunResult`` in the DB layer (``investigations.result_json``).
Hypotheses, timeline, observations, graph and results are served from the
persisted ``RunResult``.
"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from autopsy.ingest.loaders import (
    load_scenario_spec,
    load_subsystem_specs,
)
from autopsy.pipeline import run_scenario
from autopsy.schemas.graph import Graph
from autopsy.schemas.results import RunResult
from autopsy.schemas.scenarios import ScenarioSpec
from backend.db import investigations as inv_repo
from backend.db import runs as run_repo
from backend.db.database import connect
from backend.db.investigations import InvestigationRecord, update_investigation_status
from backend.db.runs import RunRecord
from backend.exceptions import BadRequestError, NotFoundError
from backend.schemas.catalog import (
    FaultConfig,
    FaultOptionResponse,
    ScenarioDetailResponse,
    ScenarioInjectionResponse,
    ScenarioListResponse,
    ScenarioResponse,
    SubsystemListResponse,
    SubsystemResponse,
    TelemetryParameterResponse,
)
from backend.schemas.investigation import (
    HypothesisListResponse,
    HypothesisResponse,
    InvestigationCreate,
    InvestigationListResponse,
    InvestigationResponse,
    InvestigationStatus,
    ProgressEvent,
    TimelineEventResponse,
    TimelineResponse,
)
from backend.schemas.run import InvestigationConfig, RunCreate, RunResponse, RunStatus
from backend.services.job_queue import InMemoryJobQueue, JobQueue
from backend.timeutils import parse_iso_z, to_iso_z, utc_now

_STAGES = (
    ("ingesting", 20, "Loading scenario, telemetry, and event logs."),
    ("graphing", 40, "Building the causal and temporal graph."),
    ("analyzing", 60, "Generating competing hypotheses."),
    ("scoring", 80, "Ranking hypotheses against the evidence."),
    ("completed", 100, "Investigation complete."),
)


def _scenario_dir() -> Path:
    return Path("configs/scenarios")


def _load_all_scenario_specs() -> dict[str, ScenarioSpec]:
    """Load every scenario declaration from ``configs/scenarios/*.yaml``.

    Scenarios are keyed by file stem so that ``POST /investigations`` and
    ``python -m autopsy run`` use the same identifier for a scenario.
    """
    specs: dict[str, ScenarioSpec] = {}
    for path in sorted(_scenario_dir().glob("*.yaml")):
        spec = load_scenario_spec(path)
        specs[path.stem] = spec
    return specs


def _get_scenario_spec(scenario_id: str) -> ScenarioSpec:
    specs = _load_all_scenario_specs()
    spec = specs.get(scenario_id.strip())
    if spec is None:
        raise NotFoundError("Scenario", scenario_id)
    return spec


def _subsystem_responses(spec: ScenarioSpec) -> list[SubsystemResponse]:
    specs = load_subsystem_specs("configs/subsystems")
    items: list[SubsystemResponse] = []
    for subsystem_id in spec.subsystems:
        sub = specs.get(subsystem_id)
        if sub is None:
            continue
        items.append(
            SubsystemResponse(
                id=sub.id,
                name=sub.name,
                description=sub.description,
                depends_on=list(sub.dependencies),
            )
        )
    return items


def _fault_option_response(spec: ScenarioSpec) -> FaultOptionResponse:
    return FaultOptionResponse(
        fault_type=spec.fault.fault_type,
        description=(
            f"{spec.fault.fault_type.value} on {spec.fault.target_subsystem}"
        ),
        target_subsystems=[spec.fault.target_subsystem],
        min_duration_seconds=60.0,
        max_duration_seconds=float(spec.duration_seconds),
        min_magnitude=0.0,
        max_magnitude=float(spec.fault.magnitude),
    )


def _spec_to_response(stem: str, spec: ScenarioSpec) -> ScenarioResponse:
    return ScenarioResponse(
        id=stem,
        name=spec.name,
        description=spec.description,
        duration_seconds=spec.duration_seconds,
        subsystem_ids=list(spec.subsystems),
        fault_types=[spec.fault.fault_type],
    )


def _spec_to_detail(stem: str, spec: ScenarioSpec) -> ScenarioDetailResponse:
    base = _spec_to_response(stem, spec).model_dump()
    subsystem_specs = load_subsystem_specs("configs/subsystems")
    return ScenarioDetailResponse(
        **base,
        mission_start_utc=spec.mission_start_utc,
        subsystems=_subsystem_responses(spec),
        telemetry_parameters=[
            TelemetryParameterResponse(
                parameter=parameter.name,
                subsystem=subsystem_id,
                unit=parameter.unit,
                nominal_value=(
                    (parameter.nominal_min + parameter.nominal_max) / 2.0
                    if parameter.nominal_min is not None
                    and parameter.nominal_max is not None
                    else 0.0
                ),
                description=parameter.description,
            )
            for subsystem_id in spec.subsystems
            for parameter in (
                subsystem_specs.get(subsystem_id).monitored_parameters
                if subsystem_specs.get(subsystem_id) is not None
                else []
            )
        ],
        fault_options=[_fault_option_response(spec)],
    )


def _record_to_response(record: InvestigationRecord) -> InvestigationResponse:
    return InvestigationResponse(
        id=record.id,
        scenario_id=record.scenario_id,
        title=record.title,
        description=record.description,
        fault_type=record.fault_type,
        status=InvestigationStatus(record.status),
        progress=record.progress,
        current_stage=record.current_stage,
        error_message=record.error_message,
        created_at=parse_iso_z(record.created_at),
        updated_at=parse_iso_z(record.updated_at),
        completed_at=(
            parse_iso_z(record.completed_at) if record.completed_at is not None else None
        ),
    )


def _hypothesis_response(hyp: Any) -> HypothesisResponse:
    return HypothesisResponse(
        hypothesis_id=hyp.hypothesis_id,
        title=hyp.title,
        summary=hyp.summary,
        causal_chain=list(hyp.causal_chain),
        evidence_ids=list(hyp.evidence_ids),
        contradiction_ids=list(hyp.contradiction_ids),
        assumptions=list(hyp.assumptions),
        confidence=hyp.confidence,
        score=hyp.score,
    )


def _result_to_timeline(result: Any, started: Any) -> TimelineResponse:
    """Build a chronological timeline from the pipeline's observations/events."""
    events: list[TimelineEventResponse] = []
    observations = list(getattr(result, "observations", []) or [])
    observations.sort(key=lambda o: o.timestamp)
    for obs in observations[:8]:
        events.append(
            TimelineEventResponse(
                event_id=f"evt_result_{obs.observation_id}",
                timestamp=obs.timestamp,
                subsystem=obs.subsystem,
                event_type=obs.observation_type,
                description=obs.description,
                severity=obs.severity,
                metadata={"observation_id": obs.observation_id},
            )
        )
    if not events:
        events.append(
            TimelineEventResponse(
                event_id=f"evt_result_{str(uuid.uuid4().hex)[:8]}",
                timestamp=started,
                subsystem="system",
                event_type="investigation_started",
                description="Investigation started.",
                severity="info",
                metadata={},
            )
        )
    return TimelineResponse(investigation_id="", events=events)


class AutopsyInvestigationService:
    """Real implementation of the investigation service contract."""

    def __init__(
        self,
        database_path: Path,
        llm: Any | None = None,
        job_queue: JobQueue | None = None,
    ) -> None:
        self._database_path = database_path
        self._llm = llm
        self._job_queue = job_queue or InMemoryJobQueue()
        self._lock = threading.RLock()
        # In-process result cache keyed by investigation id. The authoritative
        # copy is also persisted to ``investigations.result_json``.
        self._results: dict[str, Any] = {}
        self._progress: dict[str, list[dict[str, Any]]] = {}

    # ------------------------------------------------------------------ create
    def create(self, payload: InvestigationCreate) -> InvestigationResponse:
        scenario_id = payload.scenario_id.strip()
        if not scenario_id:
            raise BadRequestError("scenario_id must not be blank.")
        # The autopsy pipeline reads scenarios from configs/scenarios; validate
        # against those so the API scenario ids match the CLI (`autopsy run <id>`).
        _get_scenario_spec(scenario_id)

        now = to_iso_z(utc_now())
        identifier = f"inv_{uuid.uuid4().hex}"
        fault_type = payload.fault_type
        if fault_type is None and payload.fault_config is not None:
            fault_type = payload.fault_config.fault_type.value
        record = InvestigationRecord(
            id=identifier,
            scenario_id=scenario_id,
            title=payload.title or f"Investigation of {scenario_id}",
            description=payload.description
            or "Investigation executed by the autopsy pipeline.",
            fault_type=fault_type or "unknown",
            status=InvestigationStatus.RUNNING.value,
            progress=0,
            current_stage="ingesting",
            error_message=None,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        inv_repo.insert_investigation(self._database_path, record)
        with self._lock:
            self._progress[identifier] = []

        self._job_queue.enqueue(identifier)
        thread = threading.Thread(
            target=self._run_pipeline,
            args=(identifier, scenario_id, payload),
            daemon=True,
        )
        thread.start()
        return InvestigationResponse(
            id=identifier,
            scenario_id=scenario_id,
            title=record.title,
            description=record.description,
            fault_type=record.fault_type,
            status=InvestigationStatus.RUNNING,
            progress=0,
            current_stage="ingesting",
            error_message=None,
            created_at=parse_iso_z(now),
            updated_at=parse_iso_z(now),
            completed_at=None,
        )

    # ------------------------------------------------------------------ list / get
    def list(self, *, limit: int, cursor: str | None = None) -> InvestigationListResponse:
        decoded = None
        if cursor:
            try:
                decoded = inv_repo.decode_cursor(cursor)
            except ValueError as exc:
                raise BadRequestError(
                    "The pagination cursor is invalid or expired.",
                    code="invalid_cursor",
                ) from exc

        records, has_more = inv_repo.list_investigations(
            self._database_path,
            limit=limit,
            cursor=decoded,
        )
        next_cursor = inv_repo.encode_cursor(records[-1]) if has_more and records else None
        return InvestigationListResponse(
            items=[self._record_to_response_with_result(record) for record in records],
            next_cursor=next_cursor,
        )

    def _record_to_response_with_result(self, record: InvestigationRecord) -> InvestigationResponse:
        resp = _record_to_response(record)
        with self._lock:
            result = self._results.get(record.id)
        if result is not None:
            resp.status = InvestigationStatus.COMPLETED
            resp.progress = 100
            resp.current_stage = "completed"
            completed_at = getattr(result.timestamps, "completed_at", None)
            if completed_at is not None:
                if isinstance(completed_at, datetime):
                    resp.completed_at = completed_at
                else:
                    resp.completed_at = parse_iso_z(completed_at)
            # Surface demo metadata (mode, model, tokens) so the UI can show a mode banner.
            meta = getattr(result, "_demo", None) or {}
            if isinstance(meta, dict) and meta.get("mode"):
                resp.metadata = {"mode": meta.get("mode"), "model": meta.get("models", {}).get("reasoning")}
        return resp

    def get(self, investigation_id: str) -> InvestigationResponse:
        record = inv_repo.get_investigation(self._database_path, investigation_id)
        if record is None:
            raise NotFoundError("Investigation", investigation_id)
        return self._record_to_response_with_result(record)

    # --------------------------------------------------------------- hypotheses
    def hypotheses(self, investigation_id: str) -> HypothesisListResponse:
        self._require(investigation_id)
        with self._lock:
            result = self._results.get(investigation_id)
        if result is None:
            # Pipeline not finished yet: return what has been produced so far.
            return HypothesisListResponse(investigation_id=investigation_id, hypotheses=[])
        hyps = sorted(
            (_hypothesis_response(h) for h in result.hypotheses),
            key=lambda h: h.score,
            reverse=True,
        )
        return HypothesisListResponse(investigation_id=investigation_id, hypotheses=hyps)

    # ------------------------------------------------------------------- timeline
    def timeline(self, investigation_id: str) -> TimelineResponse:
        self._require(investigation_id)
        with self._lock:
            result = self._results.get(investigation_id)
        started = utc_now()
        if result is not None:
            tl = _result_to_timeline(result, started)
            tl.investigation_id = investigation_id
            return tl
        record = inv_repo.get_investigation(self._database_path, investigation_id)
        started = parse_iso_z(record.created_at)
        return TimelineResponse(
            investigation_id=investigation_id,
            events=[
                TimelineEventResponse(
                    event_id=f"evt_{investigation_id[-8:]}_01",
                    timestamp=started,
                    subsystem="system",
                    event_type="investigation_started",
                    description="Investigation started; pipeline still running.",
                    severity="info",
                    metadata={},
                )
            ],
        )

    # -------------------------------------------------------------------- graph
    def graph(self, investigation_id: str) -> Graph:
        """Return the causal/temporal graph for one investigation.

        The graph is persisted as ``result_json`` when the pipeline completes;
        fall back to an empty graph when no result has been stored yet.
        """
        self._require(investigation_id)
        with self._lock:
            result = self._results.get(investigation_id)
        if result is not None:
            return result.graph
        result_json = self._get_result_json(investigation_id)
        if result_json is None:
            return Graph(nodes=[], edges=[])
        result = RunResult.model_validate(json.loads(result_json))
        return result.graph

    def _get_result_json(self, investigation_id: str) -> dict[str, Any] | None:
        with connect(self._database_path) as connection:
            row = connection.execute(
                "SELECT result_json FROM investigations WHERE id = ?",
                (investigation_id,),
            ).fetchone()
        if row is None or row["result_json"] is None:
            return None
        return json.loads(row["result_json"])

    # -------------------------------------------------------------------- SSE
    def stream_progress(self, investigation_id: str) -> Iterator[ProgressEvent]:
        self._require(investigation_id)
        with self._lock:
            events = list(self._progress.get(investigation_id, []))
            result = self._results.get(investigation_id)
        for event in events:
            yield ProgressEvent.model_validate(event)
        if result is not None:
            yield ProgressEvent(
                investigation_id=investigation_id,
                status=InvestigationStatus.COMPLETED,
                stage="completed",
                progress=100,
                message="Investigation complete.",
                timestamp=utc_now(),
            )

    # ------------------------------------------------------------------- catalog
    def scenarios(self) -> ScenarioListResponse:
        specs = _load_all_scenario_specs()
        return ScenarioListResponse(
            items=[_spec_to_response(stem, spec) for stem, spec in specs.items()]
        )

    def get_scenario(self, scenario_id: str) -> ScenarioDetailResponse:
        spec = _get_scenario_spec(scenario_id)
        return _spec_to_detail(scenario_id, spec)

    def inject_fault(
        self, scenario_id: str, fault_config: FaultConfig
    ) -> ScenarioInjectionResponse:
        spec = _get_scenario_spec(scenario_id)
        if fault_config.fault_type != spec.fault.fault_type:
            raise BadRequestError(
                f"Fault type '{fault_config.fault_type.value}' is not supported "
                f"by scenario '{scenario_id}'.",
                code="invalid_fault_type",
            )
        if fault_config.target_subsystem != spec.fault.target_subsystem:
            raise BadRequestError(
                f"Fault target '{fault_config.target_subsystem}' is not valid for "
                f"scenario '{scenario_id}'; expected '{spec.fault.target_subsystem}'.",
                code="invalid_fault_target",
            )
        return ScenarioInjectionResponse(
            injection_id=f"inj_{uuid.uuid4().hex}",
            scenario_id=scenario_id,
            fault_config=fault_config,
            effective_start_time=fault_config.start_time,
            effective_end_time=fault_config.start_time
            + timedelta(seconds=fault_config.duration_seconds),
            scenario=_spec_to_detail(scenario_id, spec),
            preview=True,
            applied=False,
        )

    def subsystems(self) -> SubsystemListResponse:
        specs = load_subsystem_specs("configs/subsystems")
        return SubsystemListResponse(
            items=[
                SubsystemResponse(
                    id=sub.id,
                    name=sub.name,
                    description=sub.description,
                    depends_on=list(sub.dependencies),
                )
                for sub in specs.values()
            ]
        )

    # -------------------------------------------------------------------- runs
    def create_run(self, payload: RunCreate) -> RunResponse:
        scenario_id = payload.scenario_id.strip()
        # The autopsy pipeline reads scenarios from configs/scenarios; validate
        # against those so the API scenario ids match the CLI (`autopsy run <id>`).
        spec = _get_scenario_spec(scenario_id)
        requested = payload.resolved_investigation_config
        fault_config = self._validate_fault(
            spec, requested.fault_config or self._default_fault(spec)
        )
        config = InvestigationConfig(
            fault_config=fault_config,
            agent_config=requested.agent_config,
            scoring_config=requested.scoring_config,
        )

        now = utc_now()
        timestamp = to_iso_z(now)
        run_id = f"run_{uuid.uuid4().hex}"
        title = payload.title or f"{spec.name} investigation"
        record = RunRecord(
            run_id=run_id,
            scenario_id=scenario_id,
            status=RunStatus.QUEUED.value,
            title=title,
            config_json=config.model_dump_json(),
            fault_config_json=fault_config.model_dump_json(),
            message="Investigation queued.",
            created_at=timestamp,
            updated_at=timestamp,
            queued_at=timestamp,
            started_at=None,
            completed_at=None,
            error_message=None,
        )
        run_repo.insert_run(self._database_path, record)
        queue_position = self._job_queue.enqueue(run_id)
        return RunResponse(
            run_id=run_id,
            scenario_id=scenario_id,
            status=RunStatus.QUEUED,
            title=title,
            investigation_config=config,
            fault_config=fault_config,
            queue_position=queue_position,
            created_at=now,
            queued_at=now,
            message="Investigation queued.",
        )

    # ------------------------------------------------------------ pipeline worker
    def _run_pipeline(
        self,
        investigation_id: str,
        scenario_id: str,
        payload: InvestigationCreate,
    ) -> None:

        def emit(stage: str, message: str, fraction: float) -> None:
            progress = int(fraction * 100)
            event = {
                "investigation_id": investigation_id,
                "status": "running",
                "stage": stage,
                "progress": progress,
                "message": message,
                "timestamp": utc_now(),
            }
            with self._lock:
                self._progress.setdefault(investigation_id, []).append(event)
            update_investigation_status(
                self._database_path,
                investigation_id,
                status=InvestigationStatus.RUNNING.value,
                progress=progress,
                current_stage=stage,
                updated_at=to_iso_z(utc_now()),
            )

        try:
            result = run_scenario(
                scenario_id,
                llm=self._llm,
                progress=emit,
            )
            with self._lock:
                self._results[investigation_id] = result
                if investigation_id in self._progress:
                    self._progress[investigation_id].append(
                        {
                            "investigation_id": investigation_id,
                            "status": "completed",
                            "stage": "completed",
                            "progress": 100,
                            "message": "Investigation complete.",
                            "timestamp": utc_now(),
                        }
                    )
            # Persist the RunResult to the DB layer.
            result_json = result.model_dump_json()
            completed_at = to_iso_z(
                result.timestamps.completed_at
                if getattr(result.timestamps, "completed_at", None)
                else utc_now()
            )
            with connect(self._database_path) as connection:
                connection.execute(
                    """
                    UPDATE investigations
                    SET status = ?, progress = 100, current_stage = 'completed',
                        updated_at = ?, completed_at = ?, result_json = ?
                    WHERE id = ?
                    """,
                    (completed_at, completed_at, result_json, investigation_id),
                )
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            with self._lock:
                self._progress.setdefault(investigation_id, []).append(
                    {
                        "investigation_id": investigation_id,
                        "status": "failed",
                        "stage": "failed",
                        "progress": 100,
                        "message": f"Investigation failed: {error_message}",
                        "timestamp": utc_now(),
                    }
                )
            with connect(self._database_path) as connection:
                connection.execute(
                    """
                    UPDATE investigations
                    SET status = ?, progress = 100, current_stage = 'failed',
                        error_message = ?, updated_at = ?, completed_at = ?
                    WHERE id = ?
                    """,
                    (
                        InvestigationStatus.FAILED.value,
                        error_message,
                        to_iso_z(utc_now()),
                        to_iso_z(utc_now()),
                        investigation_id,
                    ),
                )

    # ------------------------------------------------------------ fault helpers
    def _default_fault(self, spec: ScenarioSpec) -> FaultConfig:
        offset = min(30.0, spec.duration_seconds / 10)
        duration = min(120.0, spec.duration_seconds - offset)
        return FaultConfig(
            fault_type=spec.fault.fault_type,
            target_subsystem=spec.fault.target_subsystem,
            start_time=spec.mission_start_utc + timedelta(seconds=offset),
            duration_seconds=duration,
            magnitude=max(0.0, min(25.0, spec.fault.magnitude)),
        )

    def _validate_fault(
        self, spec: ScenarioSpec, fault_config: FaultConfig
    ) -> FaultConfig:
        if fault_config.fault_type != spec.fault.fault_type:
            raise BadRequestError(
                f"Fault type '{fault_config.fault_type.value}' is not supported "
                f"by scenario '{spec.id}'.",
                code="invalid_fault_type",
            )
        if fault_config.target_subsystem != spec.fault.target_subsystem:
            raise BadRequestError(
                f"Fault target '{fault_config.target_subsystem}' is not valid for "
                f"scenario '{spec.id}'; expected '{spec.fault.target_subsystem}'.",
                code="invalid_fault_target",
            )
        if not (
            0.0 < fault_config.duration_seconds <= spec.duration_seconds
        ):
            raise BadRequestError(
                "duration_seconds must be greater than 0 and no more than "
                f"{spec.duration_seconds} for scenario '{spec.id}'.",
                code="invalid_fault_duration",
            )
        if not (0.0 <= fault_config.magnitude <= spec.fault.magnitude):
            raise BadRequestError(
                "magnitude must be between 0 and "
                f"{spec.fault.magnitude} for scenario '{spec.id}'.",
                code="invalid_fault_magnitude",
            )

        mission_start = spec.mission_start_utc
        mission_end = mission_start + timedelta(seconds=spec.duration_seconds)
        fault_end = fault_config.start_time + timedelta(seconds=fault_config.duration_seconds)
        if fault_config.start_time < mission_start or fault_end > mission_end:
            raise BadRequestError(
                "Fault window must fall within the scenario mission window.",
                code="fault_outside_scenario",
            )
        return fault_config

    def _require(self, investigation_id: str) -> InvestigationRecord:
        record = inv_repo.get_investigation(self._database_path, investigation_id)
        if record is None:
            raise NotFoundError("Investigation", investigation_id)
        return record
