# Configuration

YAML is the source format for subsystem and scenario definitions. These
directories are intentionally empty: the subsystem and scenario YAML shapes are
not frozen yet. The core domain contracts that loaders must produce are
documented in [`docs/data-contracts.md`](../docs/data-contracts.md).

## Layout

```text
configs/
├── subsystems/
│   └── <subsystem-id>.yaml
└── scenarios/
    └── <scenario-id>.yaml
```

## Rules

- Use stable, kebab-case IDs.
- Make units explicit (`voltage_v`, `duration_s`, `temperature_c`).
- Use UTC ISO 8601 timestamps, or MET seconds with an explicit `mission_start_utc`.
- Reference subsystem IDs consistently across scenario files.
- Keep secrets out of YAML; use environment variables.
- Validate every file with a Pydantic model in `autopsy/schemas/` before use.
- Configuration is data, never executable code.

## Draft shapes (illustrative only)

The snippets below show the intended direction. They are **not** loaded by the
scaffold and are not a contract.

`configs/subsystems/eps.yaml`

```yaml
id: eps
name: Electrical Power Subsystem
depends_on:
  - solar-array
  - battery
telemetry_channels:
  - bus_voltage_v
  - bus_current_a
```

`configs/scenarios/loss-of-signal.yaml`

```yaml
id: loss-of-signal
seed: 42
duration_s: 3600
subsystems:
  - eps
  - adcs
  - comms
events: []
```

Do not implement loaders against these shapes until the subsystem and scenario
contracts are added.
