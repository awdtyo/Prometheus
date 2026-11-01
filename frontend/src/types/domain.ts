/* =============================================================================
   Domain types mirroring autopsy/schemas/ contracts and docs/api-contract.md.
   These are shared primitives used by the HTTP DTO types in src/types/api.ts.
   ============================================================================= */

/** Opaque identifier (1-128 chars, starts with ASCII letter or digit) */
export type EntityId = string;

/** Lowercase kebab-case subsystem identifier */
export type SubsystemId = string;

/** Parameter/channel name */
export type ParameterName = string;

/** Lowercase snake_case type name */
export type TypeName = string;

/** Severity levels */
export type Severity = "info" | "low" | "medium" | "high" | "critical";

/** Run lifecycle status */
export type RunStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

/** Evidence category */
export type EvidenceType =
  | "telemetry"
  | "event"
  | "observation"
  | "graph_relation"
  | "external_report";

/** Evidence stance */
export type EvidenceStance = "supports" | "contradicts";

/** Fault type */
export type FaultType =
  | "power_loss"
  | "power_degradation"
  | "thermal_overheat"
  | "sensor_drift"
  | "sensor_failure"
  | "communication_loss"
  | "actuator_failure"
  | "software_fault"
  | "unknown";

/** Graph node type */
export type NodeType =
  | "subsystem"
  | "parameter"
  | "telemetry"
  | "event"
  | "observation"
  | "evidence"
  | "hypothesis";

/** Graph relationship type */
export type RelationshipType =
  | "TEMPORAL_PRECEDENCE"
  | "SUBSYSTEM_DEPENDENCY"
  | "OBSERVED_CORRELATION"
  | "CAUSAL_HYPOTHESIS"
  | "CONTRADICTS";

/** JSON-serializable object (no NaN/inf) */
export type JsonObject = Record<string, unknown>;

/** Human-readable label (1-512 chars) */
export type Label = string;

/** Description is a string with 1-4000 chars */
export type Description = string;

/* =============================================================================
   Run timestamps
   ============================================================================= */

export interface RunTimestamps {
  created_at: string; // ISO 8601 UTC
  started_at?: string | null; // ISO 8601 UTC or null
  completed_at?: string | null; // ISO 8601 UTC or null
}

/* =============================================================================
   Observation summary
   ============================================================================= */

export interface ObservationSummary {
  observation_id: EntityId;
  timestamp: string; // ISO 8601 UTC
  subsystem: SubsystemId;
  observation_type: TypeName;
  description: string;
  observed_value: number;
  threshold?: number | null;
  severity: Severity;
  source_ids: EntityId[];
}

/* =============================================================================
   Graph summaries (serializable snapshots)
   ============================================================================= */

export interface GraphSummary {
  nodes: NodeSummary[];
  edges: EdgeSummary[];
}

export interface NodeSummary {
  node_id: EntityId;
  node_type: NodeType;
  label: string;
  timestamp?: string | null;
  metadata: JsonObject;
}

export interface EdgeSummary {
  edge_id: EntityId;
  source: EntityId;
  target: EntityId;
  relationship_type: RelationshipType;
  evidence_ids: EntityId[];
  confidence: number;
  metadata: JsonObject;
}

/* =============================================================================
   Hypothesis summary
   ============================================================================= */

export interface HypothesisSummary {
  hypothesis_id: EntityId;
  title: string;
  summary: string;
  causal_chain: string[];
  evidence_ids: EntityId[];
  contradiction_ids: EntityId[];
  assumptions: string[];
  confidence: number;
  score: number;
  status: RunStatus;
}

/* =============================================================================
   Scenario summary
   ============================================================================= */

export interface ScenarioSummary {
  scenario_id: EntityId;
  name: string;
  description: string;
  mission_start_utc: string;
  subsystems: SubsystemId[];
}

/* =============================================================================
   Evaluation metrics
   Full 12-field wire shape per docs/api-contract.md (decision f).
   ============================================================================= */

export interface EvaluationMetrics {
  root_cause_accuracy: number;
  runtime_seconds: number;
  evidence_weight: number;
  consistency_weight: number;
  coverage_weight: number;
  contradiction_penalty: number;
  fault_localization_accuracy: number;
  causal_chain_accuracy: number;
  evidence_coverage: number;
  temporal_ordering_accuracy: number;
  contradiction_handling: number;
  unsupported_claim_rate: number;
}

/* =============================================================================
   Causal graph edge/node rendered by the UI (derived from API data).
   ============================================================================= */

export interface GraphNode {
  id: EntityId;
  label: string;
  type: NodeType;
  subsystem?: SubsystemId | null;
  timestamp?: string | null;
  x: number;
  y: number;
  metadata: JsonObject;
}

export interface GraphEdge {
  id: EntityId;
  source: EntityId;
  target: EntityId;
  relationship_type: RelationshipType;
  confidence: number;
  dashed: boolean;
  metadata: JsonObject;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}
