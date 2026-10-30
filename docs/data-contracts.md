# Data Contracts

> **Status: placeholder.** No contract in this document is final. Implementations
> must wait for review by all three developers. The source of truth will be
> Pydantic models in `autopsy/models/` once the contracts are agreed.

## Purpose

This document will define the typed data exchanged between ingestion, graph
construction, simulation, agents, analysis, and persistence. It is intentionally
empty of field-level schemas in the scaffold so the team does not build against
an accidental contract.

## Proposed conventions

These are proposals for discussion, not decisions:

- **Time:** UTC ISO 8601 strings with a `Z` suffix; no naive local timestamps.
- **Units:** explicit in field names or a companion metadata object (`voltage_v`,
  `duration_s`, `temperature_c`). Never rely on implicit units.
- **Identifiers:** stable, opaque strings; subsystem and scenario IDs are
  kebab-case and referenced consistently across YAML, fixtures, and the API.
- **Missing data:** explicit `null` plus a quality/flag field; never silently
  zero-fill telemetry.
- **Validation:** Pydantic v2 models with strict field types and documented
  constraints. Parsing errors are domain errors, not raw pandas/PyYAML errors.
- **Serialization:** JSON-compatible output; export JSON Schema for the frontend
  once the models stabilize.
- **Versioning:** add a contract version before external consumers depend on the
  shapes.

## Candidate entities

The following concepts are expected to appear. Their fields, relationships, and
cardinalities are **not defined yet**.

| Entity             | Purpose                                                              | Status  |
| ------------------ | -------------------------------------------------------------------- | ------- |
| `TelemetryFrame`   | One timestamped sample across one or more channels                   | Draft   |
| `TelemetryChannel` | Channel metadata: unit, sampling rate, limits, subsystem             | Draft   |
| `EventLogEntry`    | Discrete mission event with source, severity, and timestamp          | Draft   |
| `Subsystem`        | Spacecraft subsystem definition and criticality                      | Draft   |
| `Dependency`       | Directed dependency edge between subsystems                          | Draft   |
| `Scenario`         | Initial conditions, timeline, injected events, and random seed       | Draft   |
| `Investigation`    | A single reconstruction request and its lifecycle status             | Draft   |
| `Hypothesis`       | One candidate causal explanation with supporting/contradicting evidence | Draft |
| `Evidence`         | A reference to telemetry, an event, or a graph relation              | Draft   |
| `RankedNarrative`  | Ordered sequence of events plus confidence and rationale             | Draft   |

## Open questions

- What telemetry formats must be supported first (CSV, Parquet, JSON lines)?
- What is the canonical sampling/resampling policy when channels differ?
- How is clock skew between sources represented and corrected?
- What is the subsystem taxonomy and who owns it?
- What severity vocabulary do event logs use?
- How granular must evidence be for a hypothesis to be defensible?
- Do agents return free-form rationale, structured claims, or both?
- How are competing hypotheses compared: likelihood, consistency, coverage, or a
  composite score?
- What must be persisted for an investigation to be reproducible (inputs, seed,
  model version, prompt version, outputs)?
- How long are investigation artifacts retained, and are they ever exported?

## Change process

1. Propose the change in this document with a short rationale.
2. Agree on the Pydantic model and its validation rules.
3. Add or update tests for valid and invalid payloads.
4. Update `docs/api-contract.md` if the wire format changes.
5. Update fixtures and frontend types only after the model is accepted.

## TODO

- [ ] Define telemetry frame and channel contracts.
- [ ] Define event-log contract and severity vocabulary.
- [ ] Define subsystem and dependency YAML contracts.
- [ ] Define scenario contract and deterministic seed policy.
- [ ] Define hypothesis and evidence contracts.
- [ ] Define investigation lifecycle states.
- [ ] Decide persistence schema and migration strategy.
- [ ] Publish JSON Schema for frontend consumption.
