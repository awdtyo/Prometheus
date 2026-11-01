"""Tests for autopsy.observations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from autopsy.ingest.loaders import load_ground_truth, load_investigation_inputs
from autopsy.observations import extract_observations
from autopsy.schemas.events import MissionEvent
from autopsy.schemas.observations import Observation

REPO = Path(__file__).resolve().parents[1]
SCENARIO = REPO / "configs" / "scenarios" / "battery_failure.yaml"
GROUND_TRUTH = REPO / "fixtures" / "expected" / "battery_failure_ground_truth.json"


@pytest.fixture()
def inputs():
    return load_investigation_inputs(str(SCENARIO), repository_root=str(REPO))


def test_extracts_observations(inputs):
    obs = extract_observations(inputs)
    assert len(obs) > 0


def test_unique_ids(inputs):
    obs = extract_observations(inputs)
    ids = [o.observation_id for o in obs]
    assert len(ids) == len(set(ids))


def test_valid_ids(inputs):
    obs = extract_observations(inputs)
    for o in obs:
        assert isinstance(o, Observation)
        assert len(o.source_ids) >= 1


def test_determinism(inputs):
    a = extract_observations(inputs)
    b = extract_observations(inputs)
    assert [o.observation_id for o in a] == [o.observation_id for o in b]
    assert len(a) == len(b)


def test_onset_recall(inputs):
    """Observations exist near the injected degradation onset (within tolerance)."""
    obs = extract_observations(inputs)
    gt = load_ground_truth(str(GROUND_TRUTH))
    fault_ts = gt.injected_fault.start_time
    # onset tolerance: 15 minutes
    tol = timedelta(minutes=15)
    near = [o for o in obs if abs((o.timestamp - fault_ts).total_seconds()) <= tol.total_seconds()]
    print(f"\nOnset recall: {len(near)} observations within {tol} of fault onset {fault_ts}")
    assert len(near) >= 1


def test_false_positives_nominal_window(inputs):
    """Few observations in the nominal window before the fault."""
    obs = extract_observations(inputs)
    gt = load_ground_truth(str(GROUND_TRUTH))
    fault_ts = gt.injected_fault.start_time
    nominal = [
        o for o in obs if o.timestamp < fault_ts and not o.observation_type.startswith("event_")
    ]
    print(f"\nFalse positives in nominal window: {len(nominal)}")
    assert len(nominal) <= 5


def test_precision_recall_table(inputs):
    obs = extract_observations(inputs)
    gt = load_ground_truth(str(GROUND_TRUTH))
    steps = gt.expected_causal_sequence
    # For each ground-truth step, check if any obs within 5 min on same subsystem
    tp = 0
    for step in steps:
        step_ts = step.timestamp
        step_sub = step.subsystem
        window = timedelta(minutes=5)
        matches = [
            o
            for o in obs
            if o.subsystem == step_sub
            and abs((o.timestamp - step_ts).total_seconds()) <= window.total_seconds()
        ]
        if matches:
            tp += 1
    recall = tp / len(steps) if steps else 0.0
    # precision: obs that fall within 5 min of any gt step
    matched_obs = 0
    for o in obs:
        for step in steps:
            if (
                o.subsystem == step.subsystem
                and abs((o.timestamp - step.timestamp).total_seconds())
                <= timedelta(minutes=5).total_seconds()
            ):
                matched_obs += 1
                break
    precision = matched_obs / len(obs) if obs else 0.0
    print("\nPrecision/Recall table:")
    print(f"  GT steps: {len(steps)}")
    print(f"  True positives (steps recalled): {tp}")
    print(f"  Recall: {recall:.3f}")
    print(f"  Observations: {len(obs)}")
    print(f"  Matched observations: {matched_obs}")
    print(f"  Precision: {precision:.3f}")


def test_synthetic_step():
    from autopsy.schemas.inputs import InvestigationInputs
    from autopsy.schemas.subsystems import EventSpec, ParameterSpec, SubsystemSpec
    from autopsy.schemas.telemetry import TelemetryRecord

    # Build a simple step signal
    base = datetime(2026, 1, 1, tzinfo=UTC)
    interval = 60.0
    values = [10.0] * 10 + [20.0] * 10
    telemetry = []
    for i, v in enumerate(values):
        telemetry.append(
            TelemetryRecord(
                timestamp=base + timedelta(seconds=i * interval),
                subsystem="eps",
                parameter="bus_voltage",
                value=v,
                unit="V",
                source_id="eps:bus_voltage",
            )
        )
    subsys = SubsystemSpec(
        id="eps",
        name="EPS",
        description="Power",
        monitored_parameters=[
            ParameterSpec(
                name="bus_voltage",
                unit="V",
                nominal_min=9.0,
                nominal_max=11.0,
                warning_low=8.0,
                warning_high=12.0,
                description="Bus voltage",
            )
        ],
        relevant_events=[EventSpec(event_type="mode_change", description="mode", severity="info")],
        expected_downstream_effects=["none"],
    )
    inputs = InvestigationInputs(
        scenario_id="synth",
        scenario_name="synth",
        mission_start_utc=base,
        duration_seconds=1200.0,
        sampling_interval_seconds=60.0,
        subsystems=[subsys],
        telemetry=telemetry,
        events=[
            MissionEvent(
                event_id="evt_0",
                timestamp=base,
                subsystem="eps",
                event_type="mission_start",
                description="start",
                severity="info",
                metadata={},
            )
        ],
    )
    obs = extract_observations(inputs)
    assert len(obs) >= 1


def test_synthetic_spike():
    from autopsy.schemas.inputs import InvestigationInputs
    from autopsy.schemas.subsystems import EventSpec, ParameterSpec, SubsystemSpec
    from autopsy.schemas.telemetry import TelemetryRecord

    base = datetime(2026, 1, 1, tzinfo=UTC)
    values = [10.0] * 20
    values[5] = 100.0  # spike
    telemetry = []
    for i, v in enumerate(values):
        telemetry.append(
            TelemetryRecord(
                timestamp=base + timedelta(seconds=i * 60),
                subsystem="eps",
                parameter="bus_voltage",
                value=v,
                unit="V",
                source_id="eps:bus_voltage",
            )
        )
    subsys = SubsystemSpec(
        id="eps",
        name="EPS",
        description="Power",
        monitored_parameters=[
            ParameterSpec(
                name="bus_voltage",
                unit="V",
                nominal_min=9.0,
                nominal_max=11.0,
                warning_low=8.0,
                warning_high=12.0,
                description="Bus voltage",
            )
        ],
        relevant_events=[EventSpec(event_type="mode_change", description="mode", severity="info")],
        expected_downstream_effects=["none"],
    )
    inputs = InvestigationInputs(
        scenario_id="synth",
        scenario_name="synth",
        mission_start_utc=base,
        duration_seconds=1200.0,
        sampling_interval_seconds=60.0,
        subsystems=[subsys],
        telemetry=telemetry,
        events=[
            MissionEvent(
                event_id="evt_0",
                timestamp=base,
                subsystem="eps",
                event_type="mission_start",
                description="start",
                severity="info",
                metadata={},
            )
        ],
    )
    obs = extract_observations(inputs)
    assert len(obs) >= 1


def test_synthetic_drift():
    from autopsy.schemas.inputs import InvestigationInputs
    from autopsy.schemas.subsystems import EventSpec, ParameterSpec, SubsystemSpec
    from autopsy.schemas.telemetry import TelemetryRecord

    base = datetime(2026, 1, 1, tzinfo=UTC)
    values = [10.0 + 0.5 * i for i in range(30)]
    telemetry = []
    for i, v in enumerate(values):
        telemetry.append(
            TelemetryRecord(
                timestamp=base + timedelta(seconds=i * 60),
                subsystem="eps",
                parameter="bus_voltage",
                value=v,
                unit="V",
                source_id="eps:bus_voltage",
            )
        )
    subsys = SubsystemSpec(
        id="eps",
        name="EPS",
        description="Power",
        monitored_parameters=[
            ParameterSpec(
                name="bus_voltage",
                unit="V",
                nominal_min=9.0,
                nominal_max=11.0,
                warning_low=8.0,
                warning_high=12.0,
                description="Bus voltage",
            )
        ],
        relevant_events=[EventSpec(event_type="mode_change", description="mode", severity="info")],
        expected_downstream_effects=["none"],
    )
    inputs = InvestigationInputs(
        scenario_id="synth",
        scenario_name="synth",
        mission_start_utc=base,
        duration_seconds=1800.0,
        sampling_interval_seconds=60.0,
        subsystems=[subsys],
        telemetry=telemetry,
        events=[
            MissionEvent(
                event_id="evt_0",
                timestamp=base,
                subsystem="eps",
                event_type="mission_start",
                description="start",
                severity="info",
                metadata={},
            )
        ],
    )
    obs = extract_observations(inputs)
    assert len(obs) >= 1


def test_noise_only_no_observations():
    import random

    from autopsy.schemas.inputs import InvestigationInputs
    from autopsy.schemas.subsystems import EventSpec, ParameterSpec, SubsystemSpec
    from autopsy.schemas.telemetry import TelemetryRecord

    random.seed(42)
    base = datetime(2026, 1, 1, tzinfo=UTC)
    values = [10.0 + random.gauss(0, 0.1) for _ in range(30)]
    telemetry = []
    for i, v in enumerate(values):
        telemetry.append(
            TelemetryRecord(
                timestamp=base + timedelta(seconds=i * 60),
                subsystem="eps",
                parameter="bus_voltage",
                value=v,
                unit="V",
                source_id="eps:bus_voltage",
            )
        )
    subsys = SubsystemSpec(
        id="eps",
        name="EPS",
        description="Power",
        monitored_parameters=[
            ParameterSpec(
                name="bus_voltage",
                unit="V",
                nominal_min=9.0,
                nominal_max=11.0,
                warning_low=8.0,
                warning_high=12.0,
                description="Bus voltage",
            )
        ],
        relevant_events=[EventSpec(event_type="mode_change", description="mode", severity="info")],
        expected_downstream_effects=["none"],
    )
    inputs = InvestigationInputs(
        scenario_id="synth",
        scenario_name="synth",
        mission_start_utc=base,
        duration_seconds=1800.0,
        sampling_interval_seconds=60.0,
        subsystems=[subsys],
        telemetry=telemetry,
        events=[
            MissionEvent(
                event_id="evt_0",
                timestamp=base,
                subsystem="eps",
                event_type="mission_start",
                description="start",
                severity="info",
                metadata={},
            )
        ],
    )
    obs = extract_observations(inputs)
    # noise only should produce few or no telemetry observations
    telem_obs = [o for o in obs if not o.observation_type.startswith("event_")]
    print(f"\nNoise-only telemetry obs: {len(telem_obs)}")
    assert len(telem_obs) <= 2
