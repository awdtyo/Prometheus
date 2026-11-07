"""Build the ground-truth record for a run.

This module is the fault injector's bookkeeping. It writes the true cause and
chain next to the generated mission, in ``data/ground_truth/``, which the
pipeline must never read; only ``prometheus.eval`` and tests may load it.
"""

from __future__ import annotations

from typing import Any

from prometheus.sim.scenario import Scenario


def build_ground_truth(scenario: Scenario, seed: int) -> dict[str, Any]:
    """Return the complete ground-truth document for one run."""
    start = float(scenario.fault.start_s)
    chain = [
        {
            "order": step.order,
            "subsystem": step.subsystem.value,
            "channel": step.channel,
            "direction": step.direction,
            "onset_s": start + float(step.onset_offset_s),
            "onset_offset_s": float(step.onset_offset_s),
            "ramp_s": float(step.ramp_s),
            "expected_delta": float(step.expected_delta),
            "mechanism": step.mechanism,
        }
        for step in scenario.chain
    ]
    full_effect_s = max(step["onset_s"] + step["ramp_s"] for step in chain)
    end_s = float(scenario.fault.end_s or scenario.duration_s)

    distractor_end = scenario.distractor.start_s + scenario.distractor.duration_s
    return {
        "scenario": scenario.name,
        "seed": seed,
        "title": scenario.title,
        "time_origin_utc": scenario.time_origin_utc,
        "root_cause": {
            "type": scenario.fault.type,
            "subsystem": chain[0]["subsystem"],
            "injection_start_s": start,
            "ramp_s": float(scenario.fault.ramp_s),
            "parameters": dict(scenario.fault.params),
            "description": scenario.description.strip(),
        },
        "injection_times": {
            "start_s": start,
            "full_effect_s": full_effect_s,
            "end_s": end_s,
        },
        "causal_chain": chain,
        "distractor": {
            "type": scenario.distractor.type,
            "subsystem": scenario.distractor.subsystem.value,
            "channel": scenario.distractor.channel,
            "start_s": float(scenario.distractor.start_s),
            "end_s": float(distractor_end),
            "magnitude": float(scenario.distractor.magnitude),
            "causal": False,
            "note": scenario.distractor.description,
        },
    }
