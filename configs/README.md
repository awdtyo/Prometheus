# Configuration

YAML is the source format for subsystem and scenario definitions. The files are
data, never executable code, and every file is validated by a Pydantic contract
in `autopsy/schemas/` before use.

The checked-in configuration describes a **synthetic** battery-voltage failure
demo. It is not real spacecraft configuration or mission data. See
[`fixtures/README.md`](../fixtures/README.md) for the generated telemetry, event
log, and evaluation-only ground truth.

## Layout

```text
configs/
├── subsystems/
│   ├── adcs.yaml
│   ├── comms.yaml
│   ├── eps.yaml
│   ├── obc.yaml
│   └── tcs.yaml
└── scenarios/
    └── battery_failure.yaml
```

## Subsystem specifications

Each `configs/subsystems/<id>.yaml` validates as a `SubsystemSpec`:

| Field | Meaning |
| --- | --- |
| `id` | Stable lowercase kebab-case subsystem ID. |
| `name` | Human-readable name. |
| `description` | Responsibility of the subsystem. |
| `monitored_parameters` | Telemetry parameters with units, nominal ranges, and warning/critical thresholds. |
| `dependencies` | Other subsystem IDs this subsystem depends on. |
| `relevant_events` | Event types the subsystem may emit, with descriptions and expected severity. |
| `expected_downstream_effects` | Effects expected when this subsystem degrades. |

A parameter may define low thresholds, high thresholds, or both. Thresholds are
ordered:

```text
critical_low < warning_low < nominal_min <= nominal_max < warning_high < critical_high
```

`critical_low` requires `warning_low`, and `critical_high` requires
`warning_high`. A fixed-value counter may use `nominal_min == nominal_max`.

The demo dependency graph is a DAG:

```text
eps
├── tcs
├── obc
└── adcs (also depends on obc)
    └── comms (also depends on eps and obc)
```

The loader rejects unknown dependencies, duplicate subsystem IDs, and cycles.

## Scenario specification

`configs/scenarios/battery_failure.yaml` validates as a `ScenarioSpec`:

| Field | Meaning |
| --- | --- |
| `id`, `name`, `description` | Scenario identity and purpose. |
| `seed` | Deterministic seed for fixture generation. |
| `mission_start_utc` | Mission epoch in UTC. |
| `duration_seconds` | Scenario length. |
| `sampling_interval_seconds` | Telemetry cadence. |
| `subsystems` | Participating subsystem IDs. |
| `fault` | Injected fault, expressed in mission elapsed time (MET). |
| `telemetry_file` | Relative path to the telemetry CSV. |
| `event_log_json` | Relative path to the JSON event log. |
| `event_log_csv` | Relative path to the CSV event log. |

### Fault timing

`ScenarioFaultSpec.start_met_seconds` is relative to `mission_start_utc`. The
loader/scenario code converts it with:

```text
start_time = mission_start_utc + timedelta(seconds=start_met_seconds)
```

The demo fault starts at MET `900` s, which is
`2026-03-14T08:15:00Z`, and lasts `2100` s. `to_fault_config()` produces the
absolute-UTC `FaultConfig` used by the simulator and by the evaluation-only
ground truth.

### Validation rules

- `fault.target_subsystem` must be listed in `subsystems`.
- The fault must end within `duration_seconds`.
- The sampling interval cannot exceed the duration.
- The duration must be an integer multiple of the sampling interval.
- Input paths must be relative, non-empty, and inside the repository. Absolute
  paths, `..`, `~`, and any path containing an `expected` segment are rejected.

The path rule is deliberate: scenario inputs must never point at
`fixtures/expected/`, because that directory contains evaluation-only ground
truth.

## Loading

```python
from autopsy.ingest import load_scenario_spec, load_subsystem_specs

specs = load_subsystem_specs("configs/subsystems")
scenario = load_scenario_spec("configs/scenarios/battery_failure.yaml")
fault = scenario.fault.to_fault_config(scenario.mission_start_utc)
```

Use `load_investigation_inputs("configs/scenarios/battery_failure.yaml",
repository_root=".")` to build the sanitized agent-facing aggregate. It loads
the scenario, subsystem specs, telemetry, and event log, but never reads
`fixtures/expected/`.

All loaders raise `autopsy.ingest.IngestError` on invalid configuration rather
than leaking PyYAML or Pydantic exceptions.

## Rules

- Use stable, kebab-case IDs.
- Make units explicit (`battery_voltage_v`, `duration_seconds`,
  `temperature_c`).
- Use UTC ISO 8601 timestamps, or MET seconds with an explicit
  `mission_start_utc`.
- Reference subsystem IDs consistently across scenario files.
- Keep secrets out of YAML; use environment variables.
- Validate every file with a Pydantic model in `autopsy/schemas/` before use.
- Configuration is data, never executable code.
