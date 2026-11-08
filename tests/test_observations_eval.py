"""Phase 3 evaluation: precision/recall against injected ground truth.

This module is the only place in the test suite that reads ground truth, and it
exists to answer two questions:

* did the detector recover the injected causal-chain onsets, at the right
  channel, direction and time?
* did it detect the deliberate distractor, while the later graph stage (not
  this phase) decides whether the distractor belongs in the causal chain?

Strict precision intentionally counts every unmatched telemetry observation as
a false positive, including genuine secondary effects that the simulator does
not label in the causal chain.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from prometheus.ingest import ingest_run
from prometheus.observations import extract_observations
from prometheus.sim import load_scenario, simulate, write_run

SCENARIOS = (
    "battery_voltage_drop",
    "reaction_wheel_friction",
    "heater_stuck_on",
)
SEED = 7
CHAIN_TOLERANCE_S = 1200.0
DISTRACTOR_TOLERANCE_S = 900.0


def _direction_sign(direction: str) -> int:
    return 1 if direction == "up" else -1


def _match(
    targets: list[dict[str, Any]],
    observations: list[Any],
    origin: Any,
    *,
    tolerance_s: float,
) -> tuple[int, set[str]]:
    """Greedily match targets to unused telemetry observations.

    A match requires the same canonical channel, the same direction and an
    onset close enough in time. Greedy nearest-time matching is deterministic.
    """
    used: set[str] = set()
    matched = 0
    for target in sorted(targets, key=lambda item: item["onset_s"]):
        channel = f"{target['subsystem']}.{target['channel']}"
        sign = _direction_sign(target["direction"])
        candidates = [
            observation
            for observation in observations
            if observation.channel == channel
            and observation.id not in used
            and int(observation.magnitude >= 0) * 2 - 1 == sign
            and abs(
                (observation.t_start - origin).total_seconds() - target["onset_s"]
            )
            <= tolerance_s
        ]
        if not candidates:
            continue
        best = min(
            candidates,
            key=lambda observation: abs(
                (observation.t_start - origin).total_seconds() - target["onset_s"]
            ),
        )
        used.add(best.id)
        matched += 1
    return matched, used


@pytest.fixture(scope="module")
def evaluated(tmp_path_factory: pytest.TempPathFactory) -> list[dict[str, Any]]:
    """Generate every acceptance scenario and evaluate observations once."""
    root = tmp_path_factory.mktemp("observations-eval")
    results: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        run = simulate(load_scenario(scenario), SEED)
        run_dir = root / "generated" / f"{scenario}_{SEED}"
        truth_dir = root / "ground_truth" / f"{scenario}_{SEED}"
        write_run(run, run_dir, truth_dir)

        ingested = ingest_run(run_dir)
        observations = extract_observations(ingested)
        telemetry = [
            observation
            for observation in observations.observations
            if observation.source.value == "telemetry"
        ]
        truth = json.loads(
            (truth_dir / "ground_truth.json").read_text(encoding="utf-8")
        )

        chain_matched, _ = _match(
            truth["causal_chain"],
            telemetry,
            ingested.timeline[0],
            tolerance_s=CHAIN_TOLERANCE_S,
        )
        distractor = truth.get("distractor")
        distractor_matched = 0
        if distractor is not None:
            distractor_matched, _ = _match(
                [
                    {
                        "subsystem": distractor["subsystem"],
                        "channel": distractor["channel"],
                        "direction": "up" if distractor["magnitude"] >= 0 else "down",
                        "onset_s": distractor["start_s"],
                    }
                ],
                telemetry,
                ingested.timeline[0],
                tolerance_s=DISTRACTOR_TOLERANCE_S,
            )

        results.append(
            {
                "scenario": scenario,
                "chain_total": len(truth["causal_chain"]),
                "chain_matched": chain_matched,
                "telemetry": len(telemetry),
                "distractor": distractor_matched,
                "events": len(observations.observations) - len(telemetry),
            }
        )
    return results


def test_chain_recall(evaluated: list[dict[str, Any]]) -> None:
    matched = sum(item["chain_matched"] for item in evaluated)
    total = sum(item["chain_total"] for item in evaluated)
    assert matched / total >= 0.7, f"aggregate recall {matched}/{total}"


def test_strict_precision(evaluated: list[dict[str, Any]]) -> None:
    matched = sum(item["chain_matched"] for item in evaluated)
    telemetry = sum(item["telemetry"] for item in evaluated)
    assert matched / telemetry >= 0.35, f"strict precision {matched}/{telemetry}"


def test_every_distractor_is_detected(evaluated: list[dict[str, Any]]) -> None:
    assert all(item["distractor"] == 1 for item in evaluated)

    print("\nscenario                   chain     telemetry   strict P   distractor")
    for item in evaluated:
        precision = item["chain_matched"] / item["telemetry"]
        print(
            f"{item['scenario']:<26} "
            f"{item['chain_matched']}/{item['chain_total']:<7} "
            f"{item['telemetry']:<11} "
            f"{precision:>8.2f}   "
            f"{item['distractor']}"
        )
    matched = sum(item["chain_matched"] for item in evaluated)
    total = sum(item["chain_total"] for item in evaluated)
    telemetry = sum(item["telemetry"] for item in evaluated)
    print(
        f"{'aggregate':<26} {matched}/{total:<7} {telemetry:<11} "
        f"{matched / telemetry:>8.2f}   "
        f"{sum(item['distractor'] for item in evaluated)}/{len(evaluated)}"
    )


def test_event_observations_are_present(
    evaluated: list[dict[str, Any]],
) -> None:
    """Every scenario also contributes command/alarm observations."""
    assert all(item["events"] > 0 for item in evaluated)
