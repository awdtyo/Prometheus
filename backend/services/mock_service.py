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
from backend.db.investigations import InvestigationRecord
from backend.exceptions import BadRequestError, NotFoundError
from backend.schemas.catalog import (
    ScenarioListResponse,
    ScenarioResponse,
    SubsystemListResponse,
    SubsystemResponse,
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
from backend.timeutils import parse_iso_z, to_iso_z, utc_now

_SCENARIOS = (
    ScenarioResponse(
        id="scn_power_undervoltage",
        name="Power bus undervoltage",
        description="Battery heater fault causes a sustained bus undervoltage.",
        fault_types=["power_degradation", "power_loss"],
    ),
    ScenarioResponse(
        id="scn_thermal_overheat",
        name="Thermal control overheat",
        description="A stuck radiator valve drives a thermal-control overheat.",
        fault_types=["thermal_overheat", "actuator_failure"],
    ),
    ScenarioResponse(
        id="scn_comms_loss",
        name="Communications loss",
        description="An attitude upset interrupts the high-gain antenna link.",
        fault_types=["communication_loss", "sensor_failure"],
    ),
)

_SUBSYSTEMS = (
    SubsystemResponse(
        id="power",
        name="Power",
        description="Solar arrays, batteries, and the main power bus.",
        depends_on=["thermal-control"],
    ),
    SubsystemResponse(
        id="thermal-control",
        name="Thermal Control",
        description="Radiators, heaters, and thermal sensors.",
        depends_on=[],
    ),
    SubsystemResponse(
        id="attitude-control",
        name="Attitude Control",
        description="Star trackers, reaction wheels, and pointing control.",
        depends_on=["power"],
    ),
    SubsystemResponse(
        id="communications",
        name="Communications",
        description="Transponders and the high-gain antenna assembly.",
        depends_on=["power", "attitude-control"],
    ),
)

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


class MockInvestigationService:
    """Deterministic implementation of the investigation service contract."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

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
        return ScenarioListResponse(items=list(_SCENARIOS))

    def subsystems(self) -> SubsystemListResponse:
        return SubsystemListResponse(items=list(_SUBSYSTEMS))

    def _require(self, investigation_id: str) -> InvestigationRecord:
        record = repository.get_investigation(self._database_path, investigation_id)
        if record is None:
            raise NotFoundError("Investigation", investigation_id)
        return record
