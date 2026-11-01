# Fixtures

> **All data in this directory is synthetic.** It was generated for the Mission
> Autopsy demo and is **not** real spacecraft telemetry, a real event log, or a
> real mission failure. Values are illustrative and internally consistent; they
> have not been validated against a spacecraft power or thermal model.

The primary demo is a battery-voltage failure on a fictional spacecraft. It
follows the sequence:

1. Normal mission operation.
2. Battery-cell degradation.
3. Power-subsystem warning.
4. Reduced power availability and load shedding.
5. Downstream thermal, attitude, communications, and computing degradation.
6. Safe-mode entry and a declared mission-level failure.

## Layout

```text
fixtures/
├── telemetry/
│   └── battery_failure_telemetry.csv
├── events/
│   ├── battery_failure_events.json
│   └── battery_failure_events.csv
└── expected/
    └── battery_failure_ground_truth.json   # evaluation only
```

## Scenario

| Property | Value |
| --- | --- |
| Scenario ID | `battery-failure` |
| Mission start | `2026-03-14T08:00:00Z` |
| Duration | 3600 s |
| Sampling interval | 60 s |
| Deterministic seed | `20260314` |
| Injected fault | `power_degradation` on `eps` |
| Fault start | MET 900 s (`2026-03-14T08:15:00Z`) |
| Fault duration | 2100 s |
| Fault magnitude | `0.22` |
| Fault target | Battery cell 3, internal resistance increase `0.035 ohm` |
| Expected terminal state | `safe_mode` |

The scenario is defined in
[`configs/scenarios/battery_failure.yaml`](../configs/scenarios/battery_failure.yaml).
Subsystem definitions are in [`configs/subsystems/`](../configs/subsystems/).

## Telemetry format

`fixtures/telemetry/battery_failure_telemetry.csv` has 1,403 data rows: 61
timestamps (inclusive 08:00–09:00 UTC) × 23 monitored parameters across five
subsystems.

| Column | Type | Meaning |
| --- | --- | --- |
| `timestamp` | UTC ISO 8601 | Sample time, always `YYYY-MM-DDTHH:MM:SSZ`. |
| `subsystem` | string | Kebab-case subsystem ID: `eps`, `tcs`, `adcs`, `comms`, `obc`. |
| `parameter` | string | Parameter name declared in the subsystem YAML. |
| `value` | float | Finite scalar sample. |
| `unit` | string | Unit declared in the subsystem YAML (`V`, `A`, `degC`, `%`, `W`, `dB`, `kbps`, `rpm`, `count`, and so on). |
| `source_id` | string | Stable channel identifier, formatted `<subsystem>:<parameter>`. |

Rows are ordered by timestamp, then by subsystem ID, then by the parameter
order declared in the subsystem YAML. Every
`(timestamp, subsystem, parameter)` tuple appears exactly once. The file uses
LF line endings and a header row.

### Generation method

The checked-in CSV is the canonical fixture. It was produced deterministically
from the scenario seed using piecewise-linear operating curves plus a small
fixed pseudo-noise sequence. The generator is not part of the runtime; the
checked-in CSV is the source of truth for tests and demos. No random values are
generated at runtime. If the fixture is regenerated, the timeline, thresholds,
row ordering, and schema must remain unchanged.

Battery terminal voltage follows the approximate profile below; the warning
threshold is `26.2 V` and the critical threshold is `24.8 V`.

| MET | UTC | Battery voltage |
| --- | --- | --- |
| 0 s | 08:00 | ~28.6 V |
| 900 s | 08:15 | ~28.6 V |
| 1500 s | 08:25 | ~25.9 V |
| 2100 s | 08:35 | ~25.0 V |
| 2400 s | 08:40 | ~24.76 V |
| 3600 s | 09:00 | ~23.8 V |

State of charge ends near `69%`, above the `20%` critical limit. The spacecraft
reaches safe mode rather than a total power loss.

## Event-log format

The JSON file is an array of `MissionEvent` objects. The CSV file contains the
same 19 events with the same fields; the `metadata` column is a compact JSON
object encoded as a string.

| Column | Type | Meaning |
| --- | --- | --- |
| `event_id` | string | Stable ID, `evt_001` through `evt_019`. |
| `timestamp` | UTC ISO 8601 | Event time. |
| `subsystem` | string | Emitting subsystem ID. |
| `event_type` | string | Lowercase snake_case event type declared by that subsystem. |
| `description` | string | Human-readable explanation. |
| `severity` | enum | `info`, `low`, `medium`, `high`, or `critical`. |
| `metadata` | JSON object | Event-specific values such as thresholds, measured values, and MET. |

### Timeline

| UTC | Subsystem | Event | Severity |
| --- | --- | --- | --- |
| 08:00:00 | `obc` | `mission_start` | info |
| 08:05:00 | `comms` | `downlink_started` | info |
| 08:10:00 | `eps` | `battery_cell_imbalance` | medium |
| 08:15:00 | `eps` | `battery_degradation_onset` | medium |
| 08:24:00 | `eps` | `battery_voltage_sag` | high |
| 08:25:00 | `eps` | `load_shedding_started` | high |
| 08:25:30 | `tcs` | `heater_power_shed` | medium |
| 08:26:00 | `eps` | `power_available_reduced` | high |
| 08:27:00 | `tcs` | `thermal_control_degraded` | medium |
| 08:28:00 | `adcs` | `attitude_control_degraded` | high |
| 08:30:00 | `comms` | `transmitter_power_reduced` | high |
| 08:32:00 | `obc` | `cpu_load_high` | medium |
| 08:34:00 | `obc` | `watchdog_reset` | high |
| 08:35:00 | `obc` | `safe_mode_entered` | critical |
| 08:36:00 | `comms` | `downlink_degraded` | high |
| 08:40:00 | `eps` | `battery_critical` | critical |
| 08:42:00 | `tcs` | `battery_temperature_high` | high |
| 08:45:00 | `obc` | `mission_level_failure` | critical |
| 08:50:00 | `obc` | `safe_mode_stable` | high |

The event log is an observation available to the investigation. It is **not**
ground truth: a hypothesis agent may use these events, but it must still infer
the root cause and causal ordering.

## Ground truth: evaluation only

`fixtures/expected/battery_failure_ground_truth.json` contains:

| Field | Meaning |
| --- | --- |
| `scenario_id` | Scenario the ground truth belongs to. |
| `synthetic` | Always `true` for this demo. |
| `injected_fault` | Absolute-UTC `FaultConfig` that was actually injected. |
| `expected_causal_sequence` | 17 ordered `GroundTruthStep` objects from precursor to terminal state. |
| `expected_terminal_state` | `safe_mode`. |
| `notes` | Evaluation notes and the ground-truth boundary reminder. |

Each causal step has `step`, `timestamp`, `subsystem`, `event_type`,
`description`, and `evidence_ids`. The evidence IDs refer to event IDs in the
event log.

### Boundary rule

**Never include the ground-truth file, or any object loaded from it, in the
inputs passed to hypothesis agents.** The agent-facing aggregate is
`InvestigationInputs`; it deliberately has no `fault`, `ground_truth`, or
`expected_causal_sequence` field. Only `load_ground_truth()` reads this file, and
it is intended for the evaluation/scoring stage.

Scenario input paths are validated by `InputPath`: absolute paths, `..`, `~`,
empty paths, and any path containing an `expected` segment are rejected. This
keeps a scenario from accidentally wiring evaluation data into agent inputs.

## Loading and validation

```python
from autopsy.ingest import (
    load_events_json,
    load_ground_truth,
    load_investigation_inputs,
    load_subsystem_specs,
    load_telemetry_csv,
)

specs = load_subsystem_specs("configs/subsystems")
telemetry = load_telemetry_csv("fixtures/telemetry/battery_failure_telemetry.csv")
events = load_events_json("fixtures/events/battery_failure_events.json")

# Agent-facing input: no fault injection and no ground truth.
inputs = load_investigation_inputs(
    "configs/scenarios/battery_failure.yaml",
    repository_root=".",
)

# Evaluation only: keep this out of agent prompts and inputs.
ground_truth = load_ground_truth(
    "fixtures/expected/battery_failure_ground_truth.json"
)
```

Run the demo-data tests with:

```bash
pytest tests/test_demo_fixtures.py
```

The loaders raise `autopsy.ingest.IngestError` for unreadable files, invalid
YAML/CSV/JSON, schema violations, duplicate or out-of-order records, undeclared
parameters, unit mismatches, and undeclared event types.

## Assumptions and limitations

- The spacecraft, its orbit, and its operational context are fictional.
- The power model is intentionally simple: a degraded battery cell raises
  internal resistance, terminal voltage sags under load, and the EPS sheds
  non-essential loads.
- Downstream effects are scripted to be plausible and causally ordered; they are
  not a coupled multi-physics simulation.
- The event log and telemetry are consistent with each other, but the event
  descriptions are not generated from the telemetry by a simulator.
- The scenario has no sensor noise model beyond a small deterministic
  pseudo-noise term, no clock skew, no missing samples, and no packet loss.
- Safe mode is the terminal state. The mission-level failure is a declared
  operational outcome, not a complete loss of the spacecraft.
