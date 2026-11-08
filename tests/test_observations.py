"""Tests for Phase 3 observation extraction.

Synthetic channels exercise each detector at a known time; the generated
mission exercises the full ingest -> observe path, event conversion, stable
identifiers and the CLI. Ground truth is not read here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

import prometheus.cli as cli
from prometheus.contracts import (
    Channel,
    Observation,
    ObservationKind,
    ObservationSet,
    ObservationSource,
    Severity,
    Subsystem,
)
from prometheus.ingest import ingest_run
from prometheus.ingest.telemetry import ChannelSeries
from prometheus.observations import (
    Detection,
    extract_observations,
    merge_detections,
    suppress_overlaps,
)
from prometheus.observations.detect import (
    detect_channel,
    detect_drifts,
    detect_variance_changes,
)
from prometheus.sim import load_scenario, simulate, write_run

SCENARIO = "battery_voltage_drop"
SEED = 7
INTERVAL_S = 10
ORIGIN = pd.Timestamp("2026-01-01T00:00:00Z")


def _series(values: np.ndarray, interval_s: float = INTERVAL_S):
    """Build a synthetic channel with a canonical power channel name."""
    channel = Channel(
        name="power.bus_voltage_v",
        subsystem=Subsystem.POWER,
        source_name="bus_voltage_v",
        column="bus_voltage_v",
        unit="V",
        original_unit="V",
        nominal_min=-10.0,
        nominal_max=10.0,
    )
    timestamps = pd.date_range(ORIGIN, periods=len(values), freq=f"{interval_s}s")
    return ChannelSeries(
        channel=channel,
        sample_interval_s=interval_s,
        timestamp=timestamps,
        values=np.asarray(values, dtype=float),
    )


def _filtered(series) -> list[Detection]:
    """Run the same suppression/merge policy used by the pipeline."""
    detections = detect_channel(series)
    return merge_detections(suppress_overlaps(detections))


@pytest.fixture(scope="module")
def mission(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Generate one mission once for the whole module."""
    root = tmp_path_factory.mktemp("observations")
    run = simulate(load_scenario(SCENARIO), SEED)
    run_dir = root / "generated" / f"{SCENARIO}_{SEED}"
    truth_dir = root / "ground_truth" / f"{SCENARIO}_{SEED}"
    write_run(run, run_dir, truth_dir)
    return {"run_dir": run_dir, "truth_dir": truth_dir}


@pytest.fixture(scope="module")
def ingested(mission: dict[str, Any]):
    return ingest_run(mission["run_dir"])


def test_step_detected_at_change_time() -> None:
    rng = np.random.default_rng(1)
    values = rng.normal(0.0, 0.05, 721)
    values[360:] += 2.0  # step at 3600 s

    steps = [
        detection
        for detection in _filtered(_series(values))
        if detection.kind is ObservationKind.STEP
    ]

    assert steps, "step was not detected"
    detected = (steps[0].t_start - ORIGIN.to_pydatetime()).total_seconds()
    assert abs(detected - 3600.0) <= 900.0


def test_drift_detected_across_ramp() -> None:
    rng = np.random.default_rng(2)
    values = rng.normal(0.0, 0.05, 721)
    ramp = np.clip((np.arange(values.size) * INTERVAL_S - 1800.0) / 1800.0, 0.0, 1.0)
    values += 2.0 * ramp  # 1800 s ramp starting at 1800 s

    drifts = detect_drifts(_series(values))

    assert len(drifts) == 1
    drift = drifts[0]
    assert drift.kind is ObservationKind.DRIFT
    assert drift.magnitude > 1.5
    detected = (drift.t_start - ORIGIN.to_pydatetime()).total_seconds()
    assert abs(detected - 1800.0) <= 900.0
    assert (drift.t_end - ORIGIN.to_pydatetime()).total_seconds() == 7200.0


def test_spike_detected_at_peak() -> None:
    rng = np.random.default_rng(3)
    values = rng.normal(0.0, 0.05, 721)
    values[200:210] += 5.0  # spike at 2000 s

    spikes = [
        detection
        for detection in _filtered(_series(values))
        if detection.kind is ObservationKind.SPIKE
    ]

    assert len(spikes) == 1
    detected = (spikes[0].t_start - ORIGIN.to_pydatetime()).total_seconds()
    assert abs(detected - 2000.0) <= 300.0


def test_variance_change_detected() -> None:
    rng = np.random.default_rng(4)
    values = np.concatenate(
        [rng.normal(0.0, 0.1, 360), rng.normal(0.0, 1.5, 361)]
    )  # variance jump at 3600 s
    series = _series(values)

    changes = detect_variance_changes(series)

    assert changes, "variance change was not detected"
    change = changes[0]
    assert change.kind is ObservationKind.VARIANCE
    assert change.magnitude > 1.0
    detected = (change.t_start - ORIGIN.to_pydatetime()).total_seconds()
    assert abs(detected - 3600.0) <= 1200.0


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_pure_noise_produces_no_detections(seed: int) -> None:
    rng = np.random.default_rng(seed)
    values = rng.normal(0.0, 0.05, 721)

    assert _filtered(_series(values)) == []


def test_stable_ids_for_same_input(ingested) -> None:
    first = extract_observations(ingested)
    second = extract_observations(ingested)

    assert [observation.id for observation in first.observations] == [
        observation.id for observation in second.observations
    ]
    assert first.model_dump() == second.model_dump()
    assert [observation.id for observation in first.observations] == [
        f"OBS-{number:04d}" for number in range(1, len(first.observations) + 1)
    ]


def test_events_become_event_observations(ingested) -> None:
    observations = extract_observations(ingested)
    events = [
        observation
        for observation in observations.observations
        if observation.source is ObservationSource.EVENT
    ]

    unique_events = {
        (event.timestamp, event.subsystem, event.code, event.message)
        for event in ingested.events
    }
    assert len(events) == len(unique_events)
    assert events, "the mission has command/alarm rows"
    for event in events:
        assert event.kind is ObservationKind.EVENT
        assert event.channel is None
        assert event.confidence == 1.0
        assert event.magnitude == 0.0
        assert event.t_start == event.t_end
        assert ":" in event.detail


def test_duplicate_detections_are_merged() -> None:
    origin = ORIGIN.to_pydatetime()
    first = Detection(
        channel="power.bus_voltage_v",
        subsystem=Subsystem.POWER,
        kind=ObservationKind.STEP,
        t_start=origin.replace(minute=10),
        t_end=origin.replace(minute=30),
        magnitude=-1.0,
        severity=Severity.WARNING,
        confidence=0.7,
        method="quantile_shift+persistent",
    )
    second = Detection(
        channel="power.bus_voltage_v",
        subsystem=Subsystem.POWER,
        kind=ObservationKind.STEP,
        t_start=origin.replace(minute=20),
        t_end=origin.replace(minute=40),
        magnitude=-1.2,
        severity=Severity.CRITICAL,
        confidence=0.9,
        method="quantile_shift+persistent",
    )

    merged = merge_detections([first, second])

    assert len(merged) == 1
    assert merged[0].t_start == first.t_start
    assert merged[0].t_end == second.t_end
    assert merged[0].magnitude == -1.2
    assert merged[0].severity is Severity.CRITICAL
    assert merged[0].confidence == 0.9


def test_spike_inside_level_change_is_suppressed() -> None:
    origin = ORIGIN.to_pydatetime()
    level = Detection(
        channel="power.bus_voltage_v",
        subsystem=Subsystem.POWER,
        kind=ObservationKind.STEP,
        t_start=origin.replace(minute=10),
        t_end=origin.replace(minute=30),
        magnitude=-2.0,
        severity=Severity.CRITICAL,
        confidence=0.9,
        method="quantile_shift+persistent",
    )
    spike = Detection(
        channel="power.bus_voltage_v",
        subsystem=Subsystem.POWER,
        kind=ObservationKind.SPIKE,
        t_start=origin.replace(minute=11),
        t_end=origin.replace(minute=12),
        magnitude=-5.0,
        severity=Severity.CRITICAL,
        confidence=0.8,
        method="rolling_median+zscore",
    )

    kept = suppress_overlaps([level, spike])

    assert [detection.kind for detection in kept] == [ObservationKind.STEP]


def test_cli_writes_json_and_prints_table(mission: dict[str, Any]) -> None:
    runner = CliRunner()
    result = runner.invoke(cli.app, ["observe", str(mission["run_dir"])])

    assert result.exit_code == 0, result.output
    assert "observations:" in result.output
    assert "OBS-0001" in result.output
    assert "wrote:" in result.output

    output_path = mission["run_dir"] / "observations.json"
    assert output_path.exists()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["scenario"] == SCENARIO
    assert payload["seed"] == SEED
    assert payload["observations"]
    observation_set = ObservationSet.model_validate(payload)
    assert observation_set.observations[0].id == "OBS-0001"


def test_contract_rejects_invalid_observations() -> None:
    origin = ORIGIN.to_pydatetime()
    common = {
        "id": "OBS-0001",
        "subsystem": Subsystem.POWER,
        "t_start": origin,
        "t_end": origin,
        "magnitude": 1.0,
        "severity": Severity.INFO,
        "confidence": 0.5,
    }

    with pytest.raises(ValidationError):
        Observation(
            **common,
            kind=ObservationKind.STEP,
            source=ObservationSource.TELEMETRY,
            channel=None,
        )

    with pytest.raises(ValidationError):
        Observation(
            **common,
            kind=ObservationKind.STEP,
            source=ObservationSource.EVENT,
            channel=None,
        )

    with pytest.raises(ValidationError):
        Observation(
            **{**common, "t_start": origin.replace(minute=5)},
            kind=ObservationKind.STEP,
            source=ObservationSource.TELEMETRY,
            channel="power.bus_voltage_v",
        )

    with pytest.raises(ValidationError):
        ObservationSet(
            scenario=SCENARIO,
            observations=[
                Observation(
                    **common,
                    kind=ObservationKind.EVENT,
                    source=ObservationSource.EVENT,
                ),
                Observation(
                    **common,
                    kind=ObservationKind.EVENT,
                    source=ObservationSource.EVENT,
                ),
            ],
        )


def test_output_path_override(tmp_path: Path, mission: dict[str, Any]) -> None:
    from prometheus.observations import observe_run

    target = tmp_path / "nested" / "observations.json"
    result = observe_run(mission["run_dir"], out_path=target)

    assert result.output_path == target
    assert target.exists()
    assert result.telemetry_count > 0
