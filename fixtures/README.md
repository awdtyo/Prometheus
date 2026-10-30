# Fixtures

Synthetic sample data for tests and demos. Nothing in this directory is real
mission data.

## Layout

```text
fixtures/
├── telemetry/   # Telemetry samples (format TBD)
└── events/      # Event-log samples (format TBD)
```

## Rules

- Use synthetic or explicitly cleared data only.
- No personal data, export-controlled data, or proprietary mission data.
- Prefer small, deterministic samples with fixed seeds.
- Keep large generated datasets out of git; use `fixtures/generated/`, which is
  ignored.
- Document the source, units, and generation method alongside each fixture.

Payloads must validate against the contracts in
[`autopsy/schemas/`](../autopsy/schemas/); the on-disk file formats are still
pending. See [`docs/data-contracts.md`](../docs/data-contracts.md).
