# Data Contracts

> **Status: implemented — contract version `1.0.0`.**
> The source of truth is `autopsy/schemas/`. This document describes the models,
> their invariants, and their JSON representation. `backend/schemas/` remains a
> separate HTTP DTO layer. The simulator, graph algorithms, and AI agents are not
> implemented yet.

## 1. Purpose and scope

These contracts define the typed data exchanged between ingestion, graph
construction, simulation, hypothesis generation, analysis, and persistence. They
are deliberately independent of FastAPI and the backend package. The models are
Pydantic v2 classes; every model inherits from `AutopsyModel`.

The package exports a single public surface:

```python
from autopsy.schemas import (
    Evidence,
    Graph,
    Hypothesis,
    InvestigationConfig,
    MissionEvent,
    Observation,
    RunResult,
    TelemetryRecord,
)
```

## 2. Time convention

**All internal timestamps are UTC.** The shared `UtcDatetime` type enforces this:

1. The input must be a timezone-aware `datetime` with a UTC offset.
2. Naive datetimes are rejected with a validation error.
3. Aware values are normalized with `astimezone(UTC)` before the model is
   accepted, so two records representing the same instant compare equal.
4. JSON serialization uses ISO 8601 with a `Z` suffix, for example
   `2026-10-30T12:00:00Z`. Fractional seconds are preserved when present.

```python
from datetime import UTC, datetime, timedelta, timezone

from autopsy.schemas import TelemetryRecord

record = TelemetryRecord(
    timestamp=datetime(2026, 10, 30, 14, 0, tzinfo=timezone(timedelta(hours=2))),
    subsystem="power",
    parameter="bus_voltage",
    value=28.1,
    unit="V",
)
assert record.timestamp == datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
```

### 2.1 Relative mission elapsed time (MET)

Scenario files and external logs may express time as mission elapsed time in
seconds. Conversion happens **during ingestion, before constructing a domain
model**. Domain models never store a relative time in a timestamp field.

```text
utc_timestamp = mission_start_utc + timedelta(seconds=met_seconds)
met_seconds   = (utc_timestamp - mission_start_utc).total_seconds()
```

`mission_start_utc` must itself be an aware UTC timestamp. For example, a
scenario with `mission_start_utc = 2026-10-30T12:00:00Z` and
`start_met_seconds = 30` produces `FaultConfig.start_time =
2026-10-30T12:00:30Z`. If a future contract exposes a relative value directly,
the field name must end in `_met_seconds` and the scenario epoch must be part of
the same contract. Until then, all timestamp fields are absolute UTC.

Duration fields use seconds and carry an explicit `_seconds` suffix, such as
`FaultConfig.duration_seconds`.

## 3. Identifiers and collections

`EntityId` is an opaque, stable identifier with these constraints:

- 1–128 characters after trimming surrounding whitespace.
- Must start with an ASCII letter or digit.
- May contain letters, digits, `.`, `_`, `:`, and `-`.
- Must be unique within the scope documented by the owning model.
- Must never be reused after deletion; a new investigation gets new IDs.

Recommended format: `<prefix>_<uuid4hex>` or a natural namespaced key such as
`sub:power`, `tel:bus-1`, or `evt_001`. Prefixes are not enforced because
fixtures and imported logs use different naming schemes, but consistency within
one run is expected.

Specialized identifier types:

| Type            | Rule                                                                 | Example          |
| --------------- | -------------------------------------------------------------------- | ---------------- |
| `SubsystemId`   | Lowercase kebab-case: `^[a-z0-9]+(?:-[a-z0-9]+)*$`, max 64 characters | `thermal-control` |
| `ParameterName` | Starts with a letter/digit; letters, digits, `.`, `_`, `:`, `-`       | `bus_voltage`    |
| `TypeName`      | Lowercase snake_case: `^[a-z][a-z0-9_]*$`, max 64 characters          | `threshold_breach` |

Collections of identifiers (`source_ids`, `evidence_ids`, `contradiction_ids`)
reject duplicates. A `Graph` additionally rejects duplicate node IDs, duplicate
edge IDs, edges whose source or target is not in the same snapshot, and
self-loops. These checks make a graph snapshot self-contained and safe to
persist or send to the frontend.

## 4. Validation and JSON behavior

`AutopsyModel` configures Pydantic with:

- `extra="forbid"` — unknown fields are contract errors, not silently ignored.
- `allow_inf_nan=False` — `NaN` and infinity are rejected in numeric fields.
- `validate_assignment=True` — mutating a validated model re-runs validation.

Numeric rules:

| Field group                                      | Rule                                  |
| ------------------------------------------------ | ------------------------------------- |
| `confidence`, `reliability`, `score`, weights    | `0.0 <= value <= 1.0`                 |
| `FaultConfig.duration_seconds`                   | `> 0`                                 |
| `FaultConfig.magnitude`                          | `>= 0`                                |
| `AgentConfig.temperature`                        | `0.0 <= value <= 2.0`                 |
| `AgentConfig.max_hypotheses`                     | `1 <= value <= 20`                    |
| `evaluation_metrics` values                      | finite floats                         |
| `ScoringConfig` positive weights                 | must sum to `1.0` within `1e-6`       |

`metadata` and `parameters` are `JsonObject` values. They must be JSON
objects whose keys are strings and whose values survive
`json.dumps(..., allow_nan=False)`. This rejects arbitrary Python objects,
`NaN`, and infinity before a result reaches SQLite or the frontend.

Validation failures raise `pydantic.ValidationError`. Domain code should let
that exception surface at the ingestion boundary or translate it into a typed
domain error; raw pandas or PyYAML exceptions must not leak through the
contracts.

### 4.1 Serialization helpers

Every model inherits:

```python
payload: str = record.to_json(indent=2)
restored = TelemetryRecord.from_json(payload)
```

`to_json()` is equivalent to `model_dump_json()` and uses enum values and UTC
timestamps. `from_json()` is equivalent to `model_validate_json()`. Native
Pydantic methods remain available:

```python
data = record.model_dump(mode="json")
schema = TelemetryRecord.model_json_schema()
```

`SCHEMA_VERSION` in `autopsy/schemas/__init__.py` is the contract version
(`1.0.0`). Increment it when a breaking shape change is accepted.

## 5. Enumerations

### 5.1 `NodeType`

| Value         | Meaning                                             |
| ------------- | --------------------------------------------------- |
| `subsystem`   | A spacecraft subsystem                              |
| `parameter`   | A telemetry channel or measured parameter           |
| `telemetry`   | A specific telemetry sample or series               |
| `event`       | A discrete mission event                            |
| `observation` | A derived observation                               |
| `evidence`    | An evidence record                                  |
| `hypothesis`  | A competing causal explanation                      |

### 5.2 `RelationshipType`

The serialized values are the exact protocol tokens from the project
specification.

| Value                   | Direction and meaning                                                                 |
| ----------------------- | ------------------------------------------------------------------------------------- |
| `TEMPORAL_PRECEDENCE`   | `source` occurs before `target` in time.                                              |
| `SUBSYSTEM_DEPENDENCY`  | `source` depends on `target`; a failure in `target` can propagate to `source`.        |
| `OBSERVED_CORRELATION`  | `source` and `target` are observed together. The relation is symmetric; direction is for storage only and does not imply causality. |
| `CAUSAL_HYPOTHESIS`     | `source` is a proposed cause and `target` is a proposed effect.                       |
| `CONTRADICTS`           | `source` contradicts `target`, for example evidence contradicting a hypothesis.       |

### 5.3 Other enums

| Enum             | Values                                                                 |
| ---------------- | ---------------------------------------------------------------------- |
| `Severity`       | `info`, `low`, `medium`, `high`, `critical`                            |
| `RunStatus`      | `pending`, `running`, `completed`, `failed`, `cancelled`               |
| `EvidenceType`   | `telemetry`, `event`, `observation`, `graph_relation`, `external_report` |
| `EvidenceStance` | `supports`, `contradicts`                                              |
| `FaultType`      | `power_loss`, `power_degradation`, `thermal_overheat`, `sensor_drift`, `sensor_failure`, `communication_loss`, `actuator_failure`, `software_fault`, `unknown` |

## 6. Graph semantics

`Graph` is a serializable snapshot of the investigation graph. It contains
`GraphNode` and `GraphEdge` records; it is not a NetworkX object and does not
carry algorithms or mutable graph state.

- `GraphEdge.confidence` is `0.0`–`1.0`. Structural edges such as
  `SUBSYSTEM_DEPENDENCY` may use `1.0`; inferred edges use the producer's
  confidence.
- `GraphEdge.evidence_ids` cites `Evidence.evidence_id` values. It may be empty
  for structural edges, but inferred edges should cite evidence.
- `GraphEdge.source` and `GraphEdge.target` must name nodes in the same
  `Graph.nodes` collection.
- Self-loops are rejected. Multiple edges between the same pair of nodes are
  allowed when their `relationship_type` differs.
- `OBSERVED_CORRELATION` is symmetric in meaning even though it is stored as a
  directed edge. Consumers must not treat its direction as causal.

## 7. Schema reference

### 7.1 `TelemetryRecord`

One scalar sample from a telemetry channel at a UTC instant. Telemetry records
do not have their own `record_id`; `source_id` optionally identifies the
originating channel or source so observations and evidence can cite it.

| Field        | Type                  | Required | Constraints / meaning                                  |
| ------------ | --------------------- | -------- | ------------------------------------------------------ |
| `timestamp`  | `UtcDatetime`         | yes      | Sample time in UTC; naive values rejected.             |
| `subsystem`  | `SubsystemId`         | yes      | Kebab-case subsystem identifier.                       |
| `parameter`  | `ParameterName`       | yes      | Channel or parameter name.                             |
| `value`      | `float`               | yes      | Finite scalar sample.                                  |
| `unit`       | `Unit`                | yes      | Non-empty unit string, for example `V` or `degC`.      |
| `source_id`  | `SourceId \| None`    | no       | Stable source/channel identifier; defaults to `null`.  |

```json
{
  "timestamp": "2026-10-30T12:00:00Z",
  "subsystem": "power",
  "parameter": "bus_voltage",
  "value": 28.1,
  "unit": "V",
  "source_id": "tel:bus-1"
}
```

### 7.2 `MissionEvent`

A timestamped, human-meaningful event from the mission timeline.

| Field         | Type          | Required | Constraints / meaning                                      |
| ------------- | ------------- | -------- | ---------------------------------------------------------- |
| `event_id`    | `EntityId`    | yes      | Stable unique event identifier.                            |
| `timestamp`   | `UtcDatetime` | yes      | Event time in UTC.                                         |
| `subsystem`   | `SubsystemId` | yes      | Kebab-case subsystem identifier.                           |
| `event_type`  | `TypeName`    | yes      | Lowercase snake_case category, e.g. `mode_change`.         |
| `description` | `Description` | yes      | 1–4000 characters after trimming.                          |
| `severity`    | `Severity`    | yes      | Operational severity.                                      |
| `metadata`    | `JsonObject`  | no       | JSON-serializable attributes; defaults to `{}`.            |

```json
{
  "event_id": "evt_001",
  "timestamp": "2026-10-30T12:00:30Z",
  "subsystem": "power",
  "event_type": "under_voltage",
  "description": "Bus voltage fell below the safe operating limit.",
  "severity": "high",
  "metadata": {
    "limit_v": 26.0
  }
}
```

### 7.3 `Observation`

An interpretation derived from telemetry or events. Observations are the bridge
between raw evidence and graph construction. They always cite at least one
source so a hypothesis can be traced back to the original data.

| Field              | Type                | Required | Constraints / meaning                                  |
| ------------------ | ------------------- | -------- | ------------------------------------------------------ |
| `observation_id`   | `EntityId`          | yes      | Stable unique observation identifier.                  |
| `timestamp`        | `UtcDatetime`       | yes      | Observation time in UTC.                               |
| `subsystem`        | `SubsystemId`       | yes      | Kebab-case subsystem identifier.                       |
| `observation_type` | `TypeName`          | yes      | Lowercase snake_case category.                         |
| `description`      | `Description`       | yes      | Human-readable explanation.                            |
| `observed_value`   | `float`             | yes      | Finite observed value.                                 |
| `threshold`        | `float \| None`     | yes      | Threshold that makes the observation notable, or `null`. |
| `severity`         | `Severity`          | yes      | Operational severity.                                  |
| `source_ids`       | `list[EntityId]`    | yes      | At least one unique source identifier.                 |

```json
{
  "observation_id": "obs_001",
  "timestamp": "2026-10-30T12:00:30Z",
  "subsystem": "power",
  "observation_type": "threshold_breach",
  "description": "Bus voltage was below the 26 V limit for 30 seconds.",
  "observed_value": 25.4,
  "threshold": 26.0,
  "severity": "high",
  "source_ids": [
    "tel:bus-1",
    "evt_001"
  ]
}
```

### 7.4 `GraphNode`

One entity in the investigation graph.

| Field       | Type                  | Required | Constraints / meaning                                   |
| ----------- | --------------------- | -------- | ------------------------------------------------------- |
| `node_id`   | `EntityId`            | yes      | Stable unique node identifier.                          |
| `node_type` | `NodeType`            | yes      | Kind of entity represented by the node.                 |
| `label`     | `Label`               | yes      | 1–512 characters after trimming.                        |
| `timestamp` | `UtcDatetime \| None` | yes      | UTC instant when time-bound, or `null` for static nodes. |
| `metadata`  | `JsonObject`          | no       | JSON-serializable attributes; defaults to `{}`.         |

```json
{
  "node_id": "sub:power",
  "node_type": "subsystem",
  "label": "Power",
  "timestamp": "2026-10-30T12:00:00Z",
  "metadata": {
    "critical": true
  }
}
```

### 7.5 `GraphEdge`

One directed relationship between two graph nodes.

| Field               | Type                  | Required | Constraints / meaning                                  |
| ------------------- | --------------------- | -------- | ------------------------------------------------------ |
| `edge_id`           | `EntityId`            | yes      | Stable unique edge identifier.                         |
| `source`            | `EntityId`            | yes      | Source node identifier; must exist in the graph.       |
| `target`            | `EntityId`            | yes      | Target node identifier; must exist in the graph.       |
| `relationship_type` | `RelationshipType`    | yes      | Semantics of the relationship.                         |
| `evidence_ids`      | `list[EntityId]`      | no       | Unique evidence identifiers; defaults to `[]`.         |
| `confidence`        | `float`               | yes      | `0.0`–`1.0`.                                           |
| `metadata`          | `JsonObject`          | no       | JSON-serializable attributes; defaults to `{}`.        |

```json
{
  "edge_id": "edg_001",
  "source": "sub:power",
  "target": "obs_001",
  "relationship_type": "TEMPORAL_PRECEDENCE",
  "evidence_ids": [
    "ev_001"
  ],
  "confidence": 0.95,
  "metadata": {
    "note": "power precedes the observation"
  }
}
```

### 7.6 `Graph`

A self-contained snapshot of nodes and edges. Edges must reference nodes in the
same snapshot.

| Field   | Type              | Required | Constraints / meaning                         |
| ------- | ----------------- | -------- | --------------------------------------------- |
| `nodes` | `list[GraphNode]` | no       | Unique `node_id` values; defaults to `[]`.    |
| `edges` | `list[GraphEdge]` | no       | Unique `edge_id` values; defaults to `[]`.    |

```json
{
  "nodes": [
    {
      "node_id": "sub:power",
      "node_type": "subsystem",
      "label": "Power",
      "timestamp": "2026-10-30T12:00:00Z",
      "metadata": {
        "critical": true
      }
    },
    {
      "node_id": "obs_001",
      "node_type": "observation",
      "label": "Undervoltage",
      "timestamp": "2026-10-30T12:00:30Z",
      "metadata": {}
    }
  ],
  "edges": [
    {
      "edge_id": "edg_001",
      "source": "sub:power",
      "target": "obs_001",
      "relationship_type": "TEMPORAL_PRECEDENCE",
      "evidence_ids": [
        "ev_001"
      ],
      "confidence": 0.95,
      "metadata": {
        "note": "power precedes the observation"
      }
    }
  ]
}
```

### 7.7 `Evidence`

A citation that supports or contradicts a claim. `source_id` points at the
underlying telemetry record, mission event, or observation; `evidence_id` is the
stable identifier other models use when they cite this evidence.

| Field                     | Type             | Required | Constraints / meaning                               |
| ------------------------- | ---------------- | -------- | --------------------------------------------------- |
| `evidence_id`             | `EntityId`       | yes      | Stable unique evidence identifier.                  |
| `source_id`               | `EntityId`       | yes      | Stable identifier of the underlying source.         |
| `timestamp`               | `UtcDatetime`    | yes      | Time the evidence refers to, in UTC.                |
| `evidence_type`           | `EvidenceType`   | yes      | Category of the underlying source.                  |
| `description`             | `Description`    | yes      | Human-readable evidence statement.                  |
| `supports_or_contradicts` | `EvidenceStance` | yes      | Whether it supports or contradicts the claim.       |
| `reliability`             | `float`          | yes      | `0.0`–`1.0`.                                        |

```json
{
  "evidence_id": "ev_001",
  "source_id": "tel:bus-1",
  "timestamp": "2026-10-30T12:00:30Z",
  "evidence_type": "telemetry",
  "description": "Bus voltage sample below limit.",
  "supports_or_contradicts": "supports",
  "reliability": 0.98
}
```

### 7.8 `Hypothesis`

One candidate causal explanation for the observed failure. `confidence` is the
producer's belief; `score` is the analysis stage's ranking score after evidence
and contradiction weighting. Keeping them separate lets the ranking stage
change without rewriting the producer's judgment.

| Field              | Type                 | Required | Constraints / meaning                                |
| ------------------ | -------------------- | -------- | ---------------------------------------------------- |
| `hypothesis_id`    | `EntityId`           | yes      | Stable unique hypothesis identifier.                 |
| `title`            | `Label`              | yes      | 1–512 characters.                                    |
| `summary`          | `Description`        | yes      | Concise explanation.                                 |
| `causal_chain`     | `list[Description]`  | yes      | Ordered steps, at least one.                         |
| `evidence_ids`     | `list[EntityId]`     | yes      | At least one unique supporting evidence ID.          |
| `contradiction_ids`| `list[EntityId]`     | no       | Unique contradicting evidence IDs; defaults to `[]`. |
| `assumptions`      | `list[Description]`  | no       | Assumptions required for the hypothesis.             |
| `confidence`       | `float`              | yes      | `0.0`–`1.0`.                                         |
| `score`            | `float`              | yes      | `0.0`–`1.0`.                                         |

```json
{
  "hypothesis_id": "hyp_001",
  "title": "Battery heater fault caused bus undervoltage",
  "summary": "A stuck heater drained the battery and caused the bus voltage to sag.",
  "causal_chain": [
    "Heater stuck on",
    "Battery depleted",
    "Bus voltage fell"
  ],
  "evidence_ids": [
    "ev_001"
  ],
  "contradiction_ids": [],
  "assumptions": [
    "Battery state of health was nominal before the fault"
  ],
  "confidence": 0.82,
  "score": 0.79
}
```

### 7.9 `RunTimestamps`

Lifecycle timestamps for one run, all in UTC. Ordering is validated:
`created_at <= started_at <= completed_at` when the later values are present.

| Field          | Type                  | Required | Constraints / meaning                         |
| -------------- | --------------------- | -------- | --------------------------------------------- |
| `created_at`   | `UtcDatetime`         | yes      | When the run record was created.              |
| `started_at`   | `UtcDatetime \| None` | no       | When execution started.                       |
| `completed_at` | `UtcDatetime \| None` | no       | When execution reached a terminal state.      |

```json
{
  "created_at": "2026-10-30T12:00:00Z",
  "started_at": "2026-10-30T12:00:00Z",
  "completed_at": "2026-10-30T12:02:00Z"
}
```

### 7.10 `RunResult`

The serializable output of one investigation run. Observation IDs and hypothesis
IDs must be unique. `evaluation_metrics` is an open dictionary until the scoring
implementation fixes a metric vocabulary, but every value must be finite.

Status/timestamp invariants:

- `pending` — `started_at` and `completed_at` must both be `null`.
- `running` — `started_at` is required; `completed_at` must be `null`.
- `completed`, `failed`, `cancelled` — `completed_at` is required.

| Field                  | Type                   | Required | Constraints / meaning                             |
| ---------------------- | ---------------------- | -------- | ------------------------------------------------- |
| `run_id`               | `EntityId`             | yes      | Stable unique run identifier.                     |
| `scenario_id`          | `EntityId`             | yes      | Stable unique scenario identifier.                |
| `status`               | `RunStatus`            | yes      | Lifecycle state.                                  |
| `observations`         | `list[Observation]`    | no       | Unique observation IDs; defaults to `[]`.         |
| `graph`                | `Graph`                | no       | Graph snapshot; defaults to an empty graph.       |
| `hypotheses`           | `list[Hypothesis]`     | no       | Unique hypothesis IDs; defaults to `[]`.          |
| `investigation_report` | `str \| None`          | no       | Markdown report; non-empty when present.          |
| `evaluation_metrics`   | `dict[str, float]`     | no       | Finite numeric metrics; defaults to `{}`.         |
| `timestamps`           | `RunTimestamps`        | yes      | Run lifecycle timestamps.                         |

```json
{
  "run_id": "run_001",
  "scenario_id": "scn_001",
  "status": "completed",
  "observations": [
    {
      "observation_id": "obs_001",
      "timestamp": "2026-10-30T12:00:30Z",
      "subsystem": "power",
      "observation_type": "threshold_breach",
      "description": "Bus voltage was below the 26 V limit for 30 seconds.",
      "observed_value": 25.4,
      "threshold": 26.0,
      "severity": "high",
      "source_ids": [
        "tel:bus-1",
        "evt_001"
      ]
    }
  ],
  "graph": {
    "nodes": [
      {
        "node_id": "sub:power",
        "node_type": "subsystem",
        "label": "Power",
        "timestamp": "2026-10-30T12:00:00Z",
        "metadata": {
          "critical": true
        }
      },
      {
        "node_id": "obs_001",
        "node_type": "observation",
        "label": "Undervoltage",
        "timestamp": "2026-10-30T12:00:30Z",
        "metadata": {}
      }
    ],
    "edges": [
      {
        "edge_id": "edg_001",
        "source": "sub:power",
        "target": "obs_001",
        "relationship_type": "TEMPORAL_PRECEDENCE",
        "evidence_ids": [
          "ev_001"
        ],
        "confidence": 0.95,
        "metadata": {
          "note": "power precedes the observation"
        }
      }
    ]
  },
  "hypotheses": [
    {
      "hypothesis_id": "hyp_001",
      "title": "Battery heater fault caused bus undervoltage",
      "summary": "A stuck heater drained the battery and caused the bus voltage to sag.",
      "causal_chain": [
        "Heater stuck on",
        "Battery depleted",
        "Bus voltage fell"
      ],
      "evidence_ids": [
        "ev_001"
      ],
      "contradiction_ids": [],
      "assumptions": [
        "Battery state of health was nominal before the fault"
      ],
      "confidence": 0.82,
      "score": 0.79
    }
  ],
  "investigation_report": "# Report\n\nBattery heater fault.",
  "evaluation_metrics": {
    "root_cause_accuracy": 1.0,
    "runtime_seconds": 4.2
  },
  "timestamps": {
    "created_at": "2026-10-30T12:00:00Z",
    "started_at": "2026-10-30T12:00:00Z",
    "completed_at": "2026-10-30T12:02:00Z"
  }
}
```

### 7.11 `FaultConfig`

One fault injection to apply during a simulated scenario. `start_time` is an
absolute UTC instant; MET conversion happens during ingestion. `magnitude` is
interpreted in units specific to `fault_type`.

| Field              | Type          | Required | Constraints / meaning                                  |
| ------------------ | ------------- | -------- | ------------------------------------------------------ |
| `fault_type`       | `FaultType`   | yes      | Fault family to inject.                                |
| `target_subsystem` | `SubsystemId` | yes      | Kebab-case subsystem identifier.                       |
| `start_time`       | `UtcDatetime` | yes      | Fault start time in UTC.                               |
| `duration_seconds` | `float`       | yes      | `> 0`; duration in seconds.                            |
| `magnitude`        | `float`       | yes      | `>= 0`; fault-type-specific units.                     |
| `parameters`       | `JsonObject`  | no       | Optional JSON-serializable fault parameters.           |

```json
{
  "fault_type": "power_degradation",
  "target_subsystem": "power",
  "start_time": "2026-10-30T12:00:00Z",
  "duration_seconds": 120.0,
  "magnitude": 0.25,
  "parameters": {
    "rate": 0.01
  }
}
```

### 7.12 `AgentConfig`

Configuration for the hypothesis-generation stage. It is a contract only; no
agent or provider is implemented yet.

| Field            | Type             | Required | Constraints / meaning                                  |
| ---------------- | ---------------- | -------- | ------------------------------------------------------ |
| `enabled`        | `bool`           | no       | Defaults to `true`.                                    |
| `max_hypotheses` | `int`            | no       | `1`–`20`; defaults to `3`.                             |
| `temperature`    | `float`          | no       | `0.0`–`2.0`; defaults to `0.0`.                        |
| `model`          | `Label \| None`  | no       | Provider-specific model identifier.                    |
| `seed`           | `int \| None`    | no       | Deterministic seed for reproducible generation.        |
| `timeout_seconds`| `float`          | no       | `> 0`; defaults to `60.0`.                             |
| `prompt_version` | `Label \| None`  | no       | Prompt template version for reproducibility.           |

```json
{
  "enabled": true,
  "max_hypotheses": 5,
  "temperature": 0.1,
  "model": "provider/model",
  "seed": 42,
  "timeout_seconds": 60.0,
  "prompt_version": null
}
```

### 7.13 `ScoringConfig`

Weights used to rank competing hypotheses. The three positive weights must sum
to `1.0` within `1e-6`. `contradiction_penalty` is applied separately and is not
part of that sum.

| Field                  | Type    | Required | Constraints / meaning                          |
| ---------------------- | ------- | -------- | ---------------------------------------------- |
| `evidence_weight`      | `float` | no       | `0.0`–`1.0`; defaults to `0.4`.                |
| `consistency_weight`   | `float` | no       | `0.0`–`1.0`; defaults to `0.35`.               |
| `coverage_weight`      | `float` | no       | `0.0`–`1.0`; defaults to `0.25`.               |
| `contradiction_penalty`| `float` | no       | `0.0`–`1.0`; defaults to `0.2`.                |

```json
{
  "evidence_weight": 0.4,
  "consistency_weight": 0.35,
  "coverage_weight": 0.25,
  "contradiction_penalty": 0.2
}
```

### 7.14 `InvestigationConfig`

Complete input configuration for one investigation run.

| Field            | Type               | Required | Constraints / meaning                              |
| ---------------- | ------------------ | -------- | -------------------------------------------------- |
| `scenario_id`    | `EntityId`         | yes      | Stable unique scenario identifier.                 |
| `fault_config`   | `FaultConfig`      | yes      | Fault to inject for this run.                      |
| `agent_config`   | `AgentConfig`      | no       | Defaults to `AgentConfig()`.                       |
| `scoring_config` | `ScoringConfig`    | no       | Defaults to `ScoringConfig()`.                     |

```json
{
  "scenario_id": "scn_001",
  "fault_config": {
    "fault_type": "power_degradation",
    "target_subsystem": "power",
    "start_time": "2026-10-30T12:00:00Z",
    "duration_seconds": 120.0,
    "magnitude": 0.25,
    "parameters": {
      "rate": 0.01
    }
  },
  "agent_config": {
    "enabled": true,
    "max_hypotheses": 5,
    "temperature": 0.1,
    "model": "provider/model",
    "seed": 42,
    "timeout_seconds": 60.0,
    "prompt_version": null
  },
  "scoring_config": {
    "evidence_weight": 0.4,
    "consistency_weight": 0.35,
    "coverage_weight": 0.25,
    "contradiction_penalty": 0.2
  }
}
```

## 8. Change process

1. Propose the shape change with a rationale and the affected models.
2. Update the Pydantic model and its field constraints.
3. Add or update tests for valid and invalid payloads.
4. Update this document and, if the wire format changes,
   `docs/api-contract.md`.
5. Update fixtures and frontend types only after the model is accepted.
6. Increment `SCHEMA_VERSION` for breaking changes. Additive optional fields may
   keep the same major version until an external consumer depends on the shape.

## 9. Open questions

- Which telemetry formats must be supported first (CSV, Parquet, JSON lines)?
- What is the canonical sampling/resampling policy when channels differ?
- How is clock skew between sources represented and corrected?
- What is the subsystem taxonomy and who owns it?
- How do external event logs map onto `Severity` and `event_type` values?
- How granular must evidence be for a hypothesis to be defensible?
- Do agents return free-form rationale, structured claims, or both?
- What exact metric vocabulary should replace the open
  `evaluation_metrics` dictionary?
- What must be persisted for an investigation to be reproducible (inputs, seed,
  model version, prompt version, outputs)?
- How long are investigation artifacts retained, and are they ever exported?
