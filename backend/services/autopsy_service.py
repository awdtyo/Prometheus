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

import threading
import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from autopsy.pipeline import run_scenario
from backend.db import investigations as inv_repo
from backend.db import runs as run_repo
from backend.db.database import connect
from backend.db.investigations import InvestigationRecord, update_investigation_status
from backend.db.runs import RunRecord
from backend.exceptions import BadRequestError, NotFoundError
from backend.scenarios import (
    SUBSYSTEMS,
    ScenarioDefinition,
    SubsystemDefinition,
    get_scenario,
    list_scenarios,
    list_subsystems,
)
from backend.schemas.catalog import (
    FaultConfig,
    FaultOptionResponse,
    FaultType,
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


def _subsystem_response(definition: SubsystemDefinition) -> SubsystemResponse:
    return SubsystemResponse(
        id=definition.id,
        name=definition.name,
        description=definition.description,
        depends_on=list(definition.depends_on),
    )


def _scenario_summary(definition: ScenarioDefinition) -> ScenarioResponse:
    return ScenarioResponse(
        id=definition.id,
        name=definition.name,
        description=definition.description,
        duration_seconds=definition.duration_seconds,
        subsystem_ids=list(definition.subsystem_ids),
        fault_types=list(definition.fault_types),
    )


def _scenario_detail(definition: ScenarioDefinition) -> ScenarioDetailResponse:
    return ScenarioDetailResponse(
        **_scenario_summary(definition).model_dump(),
        mission_start_utc=definition.mission_start_utc,
        subsystems=[
            _subsystem_response(SUBSYSTEMS[subsystem_id])
            for subsystem_id in definition.subsystem_ids
        ],
        telemetry_parameters=[
            TelemetryParameterResponse(
                parameter=parameter.parameter,
                subsystem=parameter.subsystem,
                unit=parameter.unit,
                nominal_value=parameter.nominal_value,
                description=parameter.description,
            )
            for parameter in definition.telemetry_parameters
        ],
        fault_options=[
            FaultOptionResponse(
                fault_type=option.fault_type,
                description=option.description,
                target_subsystems=list(option.target_subsystems),
                min_duration_seconds=option.min_duration_seconds,
                max_duration_seconds=option.max_duration_seconds,
                min_magnitude=option.min_magnitude,
                max_magnitude=option.max_magnitude,
            )
            for option in definition.fault_options
        ],
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
        self._require_autopsy_scenario(scenario_id)

        now = to_iso_z(utc_now())
        identifier = f"inv_{uuid.uuid4().hex}"
        record = InvestigationRecord(
            id=identifier,
            scenario_id=scenario_id,
            title=payload.title or f"Investigation of {scenario_id}",
            description=payload.description
            or "Investigation executed by the autopsy pipeline.",
            fault_type=(payload.fault_type or "unknown"),
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
        return ScenarioListResponse(
            items=[_scenario_summary(scenario) for scenario in list_scenarios()]
        )

    def get_scenario(self, scenario_id: str) -> ScenarioDetailResponse:
        return _scenario_detail(self._require_scenario(scenario_id))

    def inject_fault(
        self, scenario_id: str, fault_config: FaultConfig
    ) -> ScenarioInjectionResponse:
        scenario = self._require_scenario(scenario_id)
        validated = self._validate_fault(scenario, fault_config)
        return ScenarioInjectionResponse(
            injection_id=f"inj_{uuid.uuid4().hex}",
            scenario_id=scenario.id,
            fault_config=validated,
            effective_start_time=validated.start_time,
            effective_end_time=validated.start_time + timedelta(seconds=validated.duration_seconds),
            scenario=_scenario_detail(scenario),
            preview=True,
            applied=False,
        )

    def subsystems(self) -> SubsystemListResponse:
        return SubsystemListResponse(
            items=[_subsystem_response(subsystem) for subsystem in list_subsystems()]
        )

    # -------------------------------------------------------------------- runs
    def create_run(self, payload: RunCreate) -> RunResponse:
        scenario_id = payload.scenario_id.strip()
        # The autopsy pipeline reads scenarios from configs/scenarios; validate
        # against those so the API scenario ids match the CLI.
        self._require_autopsy_scenario(scenario_id)
        # Catalog scenario (for fault metadata) may not exist for autopsy-only
        # scenarios; fall back to a sensible default fault configuration.
        scenario = get_scenario(scenario_id)
        requested = payload.resolved_investigation_config
        if scenario is not None:
            fault_config = self._validate_fault(
                scenario, requested.fault_config or self._default_fault(scenario)
            )
        else:
            fault_config = requested.fault_config or FaultConfig(
                fault_type=FaultType.POWER_DEGRADATION,
                target_subsystem="eps",
                start_time=utc_now(),
                duration_seconds=120.0,
                magnitude=25.0,
            )
        config = InvestigationConfig(
            fault_config=fault_config,
            agent_config=requested.agent_config,
            scoring_config=requested.scoring_config,
        )

        now = utc_now()
        timestamp = to_iso_z(now)
        run_id = f"run_{uuid.uuid4().hex}"
        title = payload.title or f"{scenario.name} investigation"
        record = RunRecord(
            run_id=run_id,
            scenario_id=scenario.id,
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
            scenario_id=scenario.id,
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
    def _default_fault(self, scenario: ScenarioDefinition) -> FaultConfig:
        option = scenario.fault_options[0]
        offset = min(30.0, scenario.duration_seconds / 10)
        duration = min(120.0, option.max_duration_seconds, scenario.duration_seconds - offset)
        return FaultConfig(
            fault_type=option.fault_type,
            target_subsystem=option.target_subsystems[0],
            start_time=scenario.mission_start_utc + timedelta(seconds=offset),
            duration_seconds=duration,
            magnitude=max(option.min_magnitude, min(25.0, option.max_magnitude)),
        )

    def _validate_fault(
        self, scenario: ScenarioDefinition, fault_config: FaultConfig
    ) -> FaultConfig:
        option = next(
            (
                candidate
                for candidate in scenario.fault_options
                if candidate.fault_type == fault_config.fault_type
            ),
            None,
        )
        if option is None:
            raise BadRequestError(
                f"Fault type '{fault_config.fault_type.value}' is not supported "
                f"by scenario '{scenario.id}'.",
                code="invalid_fault_type",
            )
        if fault_config.target_subsystem not in option.target_subsystems:
            targets = ", ".join(option.target_subsystems)
            raise BadRequestError(
                f"Fault target '{fault_config.target_subsystem}' is not valid for "
                f"scenario '{scenario.id}'; expected one of: {targets}.",
                code="invalid_fault_target",
            )
        if not (
            option.min_duration_seconds
            <= fault_config.duration_seconds
            <= option.max_duration_seconds
        ):
            raise BadRequestError(
                "duration_seconds must be between "
                f"{option.min_duration_seconds} and {option.max_duration_seconds} "
                f"for fault type '{fault_config.fault_type.value}'.",
                code="invalid_fault_duration",
            )
        if not (option.min_magnitude <= fault_config.magnitude <= option.max_magnitude):
            raise BadRequestError(
                "magnitude must be between "
                f"{option.min_magnitude} and {option.max_magnitude} "
                f"for fault type '{fault_config.fault_type.value}'.",
                code="invalid_fault_magnitude",
            )

        mission_start = scenario.mission_start_utc
        mission_end = mission_start + timedelta(seconds=scenario.duration_seconds)
        fault_end = fault_config.start_time + timedelta(seconds=fault_config.duration_seconds)
        if fault_config.start_time < mission_start or fault_end > mission_end:
            raise BadRequestError(
                "Fault window must fall within the scenario mission window.",
                code="fault_outside_scenario",
            )
        return fault_config

    def _require_scenario(self, scenario_id: str) -> ScenarioDefinition:
        scenario = get_scenario(scenario_id.strip())
        if scenario is None:
            raise NotFoundError("Scenario", scenario_id)
        return scenario

    def _require_autopsy_scenario(self, scenario_id: str) -> None:
        """Validate that the scenario exists for the autopsy pipeline
        (configs/scenarios/<id>.yaml), so API scenario ids match the CLI."""
        from pathlib import Path

        if not Path(f"configs/scenarios/{scenario_id}.yaml").exists():
            raise NotFoundError("Scenario", scenario_id)

    def _require(self, investigation_id: str) -> InvestigationRecord:
        record = inv_repo.get_investigation(self._database_path, investigation_id)
        if record is None:
            raise NotFoundError("Investigation", investigation_id)
        return record
