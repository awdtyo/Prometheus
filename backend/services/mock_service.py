"""Domain-free service used until the ``autopsy`` pipeline is wired.

The mock deliberately returns deterministic sample results. It exercises routing,
validation, persistence, pagination, problem responses, and SSE streaming without
importing simulator, graph, or agent code from the domain package.
"""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from backend.db import investigations as repository
from backend.db import runs as run_repository
from backend.db.investigations import InvestigationRecord
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
    ("queued", 0, "Investigation accepted."),
    ("ingesting", 20, "Loading scenario, telemetry, and event logs."),
    ("graphing", 40, "Building the causal and temporal graph."),
    ("simulating", 60, "Replaying the scenario."),
    ("generating_hypotheses", 80, "Generating competing hypotheses."),
    ("ranking", 95, "Ranking hypotheses against the evidence."),
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


class MockInvestigationService:
    """Deterministic implementation of the investigation service contract."""

    def __init__(self, database_path: Path, job_queue: JobQueue | None = None) -> None:
        self._database_path = database_path
        self._job_queue = job_queue or InMemoryJobQueue()

    def create(self, payload: InvestigationCreate) -> InvestigationResponse:
        scenario_id = payload.scenario_id.strip()
        if not scenario_id:
            raise BadRequestError("scenario_id must not be blank.")

        now = to_iso_z(utc_now())
        identifier = f"inv_{uuid4().hex}"
        record = InvestigationRecord(
            id=identifier,
            scenario_id=scenario_id,
            title=payload.title or f"Investigation of {scenario_id}",
            description=payload.description
            or "Mock investigation generated without the autopsy pipeline.",
            fault_type=payload.fault_type or "unknown",
            status=InvestigationStatus.COMPLETED.value,
            progress=100,
            current_stage="completed",
            error_message=None,
            created_at=now,
            updated_at=now,
            completed_at=now,
        )
        repository.insert_investigation(self._database_path, record)
        return _record_to_response(record)

    def list(self, *, limit: int, cursor: str | None = None) -> InvestigationListResponse:
        decoded = None
        if cursor:
            try:
                decoded = repository.decode_cursor(cursor)
            except ValueError as exc:
                raise BadRequestError(
                    "The pagination cursor is invalid or expired.",
                    code="invalid_cursor",
                ) from exc

        records, has_more = repository.list_investigations(
            self._database_path,
            limit=limit,
            cursor=decoded,
        )
        next_cursor = repository.encode_cursor(records[-1]) if has_more and records else None
        return InvestigationListResponse(
            items=[_record_to_response(record) for record in records],
            next_cursor=next_cursor,
        )

    def get(self, investigation_id: str) -> InvestigationResponse:
        return _record_to_response(self._require(investigation_id))

    def hypotheses(self, investigation_id: str) -> HypothesisListResponse:
        record = self._require(investigation_id)
        suffix = record.id.removeprefix("inv_")[-8:]
        hypotheses = [
            HypothesisResponse(
                hypothesis_id=f"hyp_{suffix}_01",
                title="Battery heater stuck on drained the power bus",
                summary=(
                    "A failed heater switch kept the battery heater energized, "
                    "depleting the battery and sagging the main bus voltage."
                ),
                causal_chain=[
                    "Heater switch failed closed",
                    "Battery heater stayed energized",
                    "Battery state of charge fell",
                    "Main bus voltage dropped below the safe limit",
                ],
                evidence_ids=[f"ev_{suffix}_01", f"ev_{suffix}_02"],
                contradiction_ids=[],
                assumptions=["Battery state of health was nominal before the fault"],
                confidence=0.82,
                score=0.79,
            ),
            HypothesisResponse(
                hypothesis_id=f"hyp_{suffix}_02",
                title="Solar array shadowing reduced power generation",
                summary=(
                    "An attitude excursion shadowed the solar arrays, reducing "
                    "generation and causing the observed undervoltage."
                ),
                causal_chain=[
                    "Attitude excursion changed array illumination",
                    "Solar array output dropped",
                    "Battery supplied the shortfall",
                    "Bus voltage sagged",
                ],
                evidence_ids=[f"ev_{suffix}_03"],
                contradiction_ids=[f"ev_{suffix}_04"],
                assumptions=["Array pointing telemetry is accurate"],
                confidence=0.61,
                score=0.55,
            ),
            HypothesisResponse(
                hypothesis_id=f"hyp_{suffix}_03",
                title="Bus voltage sensor drift produced a false low reading",
                summary=(
                    "The undervoltage telemetry may be a sensor artifact rather "
                    "than a physical power failure."
                ),
                causal_chain=[
                    "Voltage sensor drifted out of calibration",
                    "Reported bus voltage fell",
                    "Threshold monitor raised an alert",
                ],
                evidence_ids=[f"ev_{suffix}_05"],
                contradiction_ids=[f"ev_{suffix}_02", f"ev_{suffix}_06"],
                assumptions=["No independent voltage measurement is available"],
                confidence=0.32,
                score=0.24,
            ),
        ]
        return HypothesisListResponse(
            investigation_id=record.id,
            hypotheses=hypotheses,
        )

    def timeline(self, investigation_id: str) -> TimelineResponse:
        record = self._require(investigation_id)
        started = parse_iso_z(record.created_at)
        events = [
            TimelineEventResponse(
                event_id=f"evt_{record.id[-8:]}_01",
                timestamp=started,
                subsystem="command-and-data-handling",
                event_type="scenario_replay_started",
                description="Scenario replay began with the recorded mission inputs.",
                severity="info",
                metadata={"scenario_id": record.scenario_id},
            ),
            TimelineEventResponse(
                event_id=f"evt_{record.id[-8:]}_02",
                timestamp=started + timedelta(seconds=30),
                subsystem="power",
                event_type="telemetry_anomaly_detected",
                description="Bus voltage moved outside its nominal operating band.",
                severity="medium",
                metadata={"parameter": "bus_voltage"},
            ),
            TimelineEventResponse(
                event_id=f"evt_{record.id[-8:]}_03",
                timestamp=started + timedelta(seconds=45),
                subsystem="thermal-control",
                event_type="heater_current_high",
                description="Battery heater current remained elevated after the expected cutoff.",
                severity="high",
                metadata={"parameter": "heater_current"},
            ),
            TimelineEventResponse(
                event_id=f"evt_{record.id[-8:]}_04",
                timestamp=started + timedelta(seconds=60),
                subsystem="power",
                event_type="bus_undervoltage",
                description="Main bus voltage fell below the safe operating limit.",
                severity="critical",
                metadata={"limit_v": 26.0},
            ),
        ]
        return TimelineResponse(investigation_id=record.id, events=events)

    def stream_progress(self, investigation_id: str) -> Iterator[ProgressEvent]:
        record = self._require(investigation_id)
        terminal_status = InvestigationStatus(record.status)
        for index, (stage, progress, message) in enumerate(_STAGES):
            is_last = index == len(_STAGES) - 1
            yield ProgressEvent(
                investigation_id=record.id,
                status=terminal_status if is_last else InvestigationStatus.RUNNING,
                stage=stage,
                progress=progress,
                message=message,
                timestamp=utc_now(),
            )

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
            injection_id=f"inj_{uuid4().hex}",
            scenario_id=scenario.id,
            fault_config=validated,
            effective_start_time=validated.start_time,
            effective_end_time=validated.start_time + timedelta(seconds=validated.duration_seconds),
            scenario=_scenario_detail(scenario),
        )

    def subsystems(self) -> SubsystemListResponse:
        return SubsystemListResponse(
            items=[_subsystem_response(subsystem) for subsystem in list_subsystems()]
        )

    def create_run(self, payload: RunCreate) -> RunResponse:
        scenario = self._require_scenario(payload.scenario_id)
        requested = payload.resolved_investigation_config
        fault_config = self._validate_fault(
            scenario, requested.fault_config or self._default_fault(scenario)
        )
        config = InvestigationConfig(
            fault_config=fault_config,
            agent_config=requested.agent_config,
            scoring_config=requested.scoring_config,
        )

        now = utc_now()
        timestamp = to_iso_z(now)
        run_id = f"run_{uuid4().hex}"
        title = payload.title or f"{scenario.name} investigation"
        message = "Investigation queued."
        record = RunRecord(
            run_id=run_id,
            scenario_id=scenario.id,
            status=RunStatus.QUEUED.value,
            title=title,
            config_json=config.model_dump_json(),
            fault_config_json=fault_config.model_dump_json(),
            message=message,
            created_at=timestamp,
            updated_at=timestamp,
            queued_at=timestamp,
            started_at=None,
            completed_at=None,
            error_message=None,
        )
        run_repository.insert_run(self._database_path, record)
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
            message=message,
        )

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

    def _require(self, investigation_id: str) -> InvestigationRecord:
        record = repository.get_investigation(self._database_path, investigation_id)
        if record is None:
            raise NotFoundError("Investigation", investigation_id)
        return record
