"""Tests for the simulator, fault injector and generated artefacts.

The chain test is the important one: it re-derives each ground-truth step from
the CSV data, so a mismatch between truth and telemetry fails the suite.
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

import prometheus.cli as cli
from prometheus.sim import (
    ScenarioError,
    available_scenarios,
    load_scenario,
    simulate,
    write_run,
)
from prometheus.sim.scenario import Scenario

SEED = 11
WIN_PRE_S = 1800.0
WIN_POST_S = 1800.0


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> dict[str, dict[str, Any]]:
    """Generate every scenario once for the whole module."""
    root = tmp_path_factory.mktemp("missions")
    runs: dict[str, dict[str, Any]] = {}
    for name in available_scenarios():
        scenario = load_scenario(name)
        run = simulate(scenario, SEED)
        out_dir = root / "generated" / f"{name}_{SEED}"
        truth_dir = root / "ground_truth" / f"{name}_{SEED}"
        written = write_run(run, out_dir, truth_dir)
        runs[name] = {
            "run": run,
            "out": out_dir,
            "truth": json.loads(written.ground_truth_path.read_text()),
            "truth_path": written.ground_truth_path,
            "files": written.files,
        }
    return runs


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _specs(out_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((out_dir / "specs.yaml").read_text(encoding="utf-8"))


def _mean(rows: list[dict[str, str]], column: str) -> float:
    return statistics.fmean(float(row[column]) for row in rows)


def _slice(
    rows: list[dict[str, str]], start_s: float, end_s: float, interval: int
) -> list[dict[str, str]]:
    start = max(0, int(round(start_s / interval)))
    end = int(round(end_s / interval))
    return rows[start:end]


def test_three_scenarios_are_packaged() -> None:
    assert available_scenarios() == [
        "battery_voltage_drop",
        "heater_stuck_on",
        "reaction_wheel_friction",
    ]


def test_unknown_scenario_is_rejected() -> None:
    with pytest.raises(ScenarioError, match="available:"):
        load_scenario("solar_flare")


def test_chain_order_is_validated() -> None:
    scenario = load_scenario("battery_voltage_drop")
    payload = scenario.model_dump()
    payload["chain"] = list(reversed(payload["chain"]))

    with pytest.raises(ValidationError, match="chain order"):
        Scenario.model_validate(payload)


def test_same_seed_produces_identical_files(tmp_path: Path) -> None:
    scenario = load_scenario("battery_voltage_drop")
    for label in ("a", "b"):
        run = simulate(scenario, seed=SEED)
        write_run(
            run,
            tmp_path / label / "generated",
            tmp_path / label / "ground_truth",
        )

    files_a = sorted(path.relative_to(tmp_path / "a") for path in (tmp_path / "a").rglob("*"))
    files_b = sorted(path.relative_to(tmp_path / "b") for path in (tmp_path / "b").rglob("*"))
    assert [str(path) for path in files_a if path.is_file()] == [
        str(path) for path in files_b if path.is_file()
    ]
    for relative in (path for path in files_a if path.is_file()):
        assert (tmp_path / "a" / relative).read_bytes() == (
            tmp_path / "b" / relative
        ).read_bytes(), f"{relative} differs between identical runs"


def test_different_seed_changes_noise(tmp_path: Path) -> None:
    scenario = load_scenario("battery_voltage_drop")
    write_run(simulate(scenario, 1), tmp_path / "one", tmp_path / "gt1")
    write_run(simulate(scenario, 2), tmp_path / "two", tmp_path / "gt2")

    assert (tmp_path / "one" / "telemetry_power.csv").read_bytes() != (
        tmp_path / "two" / "telemetry_power.csv"
    ).read_bytes()


def test_negative_seed_is_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        simulate(load_scenario("heater_stuck_on"), -1)


@pytest.mark.parametrize("scenario_name", available_scenarios())
def test_chain_ordering_matches_data(
    generated: dict[str, dict[str, Any]], scenario_name: str
) -> None:
    entry = generated[scenario_name]
    specs = _specs(entry["out"])
    chain = entry["truth"]["causal_chain"]

    onsets = [step["onset_s"] for step in chain]
    assert onsets == sorted(onsets), "ground-truth chain is not time ordered"
    assert len(set(onsets)) == len(onsets), "chain steps share an onset"

    for step in chain:
        subsystem = step["subsystem"]
        layout = specs["subsystems"][subsystem]
        channel = layout["channels"][step["channel"]]
        rows = _read_csv(entry["out"] / layout["file"])
        interval = layout["sample_interval_s"]

        before = _slice(rows, step["onset_s"] - WIN_PRE_S, step["onset_s"], interval)
        after_start = step["onset_s"] + step["ramp_s"] + 60.0
        after = _slice(rows, after_start, after_start + WIN_POST_S, interval)
        assert len(before) > 10 and len(after) > 10, f"not enough samples for {step}"

        measured = _mean(after, channel["column"]) - _mean(before, channel["column"])
        expected = step["expected_delta"]
        assert measured * expected > 0, (
            f"{scenario_name} {subsystem}/{step['channel']}: measured {measured:+.3f} "
            f"has the wrong sign for expected {expected:+.3f}"
        )
        assert abs(measured) >= 0.3 * abs(expected), (
            f"{scenario_name} {subsystem}/{step['channel']}: measured {measured:+.3f} "
            f"is too weak for expected {expected:+.3f}"
        )


@pytest.mark.parametrize("scenario_name", available_scenarios())
def test_distractor_is_present_and_not_causal(
    generated: dict[str, dict[str, Any]], scenario_name: str
) -> None:
    entry = generated[scenario_name]
    specs = _specs(entry["out"])
    distractor = entry["truth"]["distractor"]
    chain_pairs = {(step["subsystem"], step["channel"]) for step in entry["truth"]["causal_chain"]}

    assert distractor["causal"] is False
    assert (distractor["subsystem"], distractor["channel"]) not in chain_pairs
    assert distractor["end_s"] <= entry["truth"]["root_cause"]["injection_start_s"]

    layout = specs["subsystems"][distractor["subsystem"]]
    channel = layout["channels"][distractor["channel"]]
    rows = _read_csv(entry["out"] / layout["file"])
    interval = layout["sample_interval_s"]

    baseline = _slice(rows, distractor["start_s"] - 300.0, distractor["start_s"], interval)
    during = _slice(rows, distractor["start_s"], distractor["end_s"], interval)
    measured = _mean(during, channel["column"]) - _mean(baseline, channel["column"])

    assert measured * distractor["magnitude"] > 0
    assert abs(measured) >= 0.3 * abs(distractor["magnitude"])

    codes = {event["code"] for event in _read_csv(entry["out"] / "events.csv")}
    assert any("SNR" in code or "INRUSH" in code or "SLEW" in code for code in codes)


@pytest.mark.parametrize("scenario_name", available_scenarios())
def test_output_layout_and_formats(
    generated: dict[str, dict[str, Any]], scenario_name: str
) -> None:
    entry = generated[scenario_name]
    names = {path.name for path in entry["out"].iterdir()}
    assert names == {
        "telemetry_power.csv",
        "telemetry_thermal.csv",
        "telemetry_comms.csv",
        "telemetry_adcs.csv",
        "events.csv",
        "specs.yaml",
    }
    assert "ground_truth.json" not in names

    power = _read_csv(entry["out"] / "telemetry_power.csv")
    thermal = _read_csv(entry["out"] / "telemetry_thermal.csv")
    comms = _read_csv(entry["out"] / "telemetry_comms.csv")
    adcs = _read_csv(entry["out"] / "telemetry_adcs.csv")
    assert power[0]["timestamp"].endswith("Z") and "T" in power[0]["timestamp"]
    assert thermal[0]["time_s"].isdigit()
    assert comms[0]["unix_ms"].isdigit() and len(comms[0]["unix_ms"]) == 13
    assert "+00:00" in adcs[0]["timestamp_utc"]
    assert power[0]["timestamp"] != thermal[0]["time_s"]
    assert float(thermal[0]["node_battery_k"]) > 250.0

    specs = _specs(entry["out"])
    for subsystem in ("power", "thermal", "comms", "adcs"):
        assert specs["subsystems"][subsystem]["channels"]
        for channel in specs["subsystems"][subsystem]["channels"].values():
            assert channel["unit"]
            assert channel["nominal_max"] > channel["nominal_min"]
    assert len(specs["dependencies"]) >= 5
    for dependency in specs["dependencies"]:
        lag_low, lag_high = dependency["lag_seconds"]
        assert 0 <= lag_low <= lag_high


@pytest.mark.parametrize("scenario_name", available_scenarios())
def test_ground_truth_is_written_outside_generated(
    generated: dict[str, dict[str, Any]], scenario_name: str
) -> None:
    entry = generated[scenario_name]
    truth_path = entry["truth_path"]
    assert truth_path.name == "ground_truth.json"
    assert "generated" not in truth_path.parts
    assert truth_path.parent.name == f"{scenario_name}_{SEED}"
    assert entry["truth"]["scenario"] == scenario_name
    assert entry["truth"]["seed"] == SEED
    assert entry["truth"]["root_cause"]["subsystem"] in {"power", "thermal", "comms", "adcs"}


def test_cli_generate(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli.app,
        [
            "sim",
            "generate",
            "battery_voltage_drop",
            "--seed",
            "5",
            "--out",
            str(tmp_path / "run"),
            "--ground-truth-out",
            str(tmp_path / "truth"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "root cause: power / battery_voltage_drop" in result.output
    assert (tmp_path / "run" / "telemetry_power.csv").is_file()
    assert (tmp_path / "truth" / "ground_truth.json").is_file()


def test_cli_reports_unknown_scenario(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli.app, ["sim", "generate", "nonexistent"])
    combined = result.output + getattr(result, "stderr", "")

    assert result.exit_code == 1
    assert "available scenarios:" in combined
