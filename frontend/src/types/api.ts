/* =============================================================================
   HTTP wire types mirroring docs/api-contract.md.
   Field naming is snake_case; timestamps are UTC ISO 8601 with a Z suffix.
   ============================================================================= */

import type {
  EntityId,
  SubsystemId,
  ParameterName,
  TypeName,
  Severity,
  RunStatus,
  FaultType,
  Graph,
  GraphEdge,
  GraphNode,
  JsonObject,
  EvaluationMetrics,
} from "./domain";

export type ConnectionStatus = "loading" | "online" | "offline";

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
}

/* -------------------------------------------------------
   Catalog
   ------------------------------------------------------- */

/** Scenario summary returned by GET /api/v1/scenarios */
export interface ScenarioSummary {
  id: EntityId;
  name: string;
  description: string;
  duration_seconds: number;
  subsystem_ids: SubsystemId[];
  fault_types: FaultType[];
}

/** Telemetry channel available in a scenario (GET /api/v1/scenarios/{id}) */
export interface TelemetryParameterResponse {
  parameter: ParameterName;
  subsystem: SubsystemId;
  unit: string;
  nominal_value: number;
  description: string;
}

/** A spacecraft subsystem and its direct dependencies */
export interface SubsystemResponse {
  id: SubsystemId;
  name: string;
  description: string;
  depends_on: SubsystemId[];
}

/** A fault type supported by a scenario and its allowed targets */
export interface FaultOptionResponse {
  fault_type: FaultType;
  description: string;
  target_subsystems: SubsystemId[];
  min_duration_seconds: number;
  max_duration_seconds: number;
  min_magnitude: number;
  max_magnitude: number;
}

/** Complete scenario configuration (GET /api/v1/scenarios/{id}) */
export interface ScenarioDetailResponse {
  id: EntityId;
  name: string;
  description: string;
  duration_seconds: number;
  subsystem_ids: SubsystemId[];
  fault_types: FaultType[];
  mission_start_utc: string;
  subsystems: SubsystemResponse[];
  telemetry_parameters: TelemetryParameterResponse[];
  fault_options: FaultOptionResponse[];
}

/** Collection of available scenarios */
export interface ScenarioListResponse {
  items: ScenarioSummary[];
}

/** Collection of subsystems */
export interface SubsystemListResponse {
  items: SubsystemResponse[];
}

/* -------------------------------------------------------
   Investigations
   ------------------------------------------------------- */

/** Current state and summary of one investigation (POST/GET /api/v1/investigations) */
export interface Investigation {
  id: EntityId;
  investigation_id: EntityId;
  scenario_id: EntityId;
  title: string;
  description: string | null;
  fault_type: FaultType | null;
  status: RunStatus;
  progress: number;
  current_stage: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

/** Cursor-paginated investigation list */
export interface InvestigationListResponse {
  items: Investigation[];
  next_cursor: string | null;
}

/** Proposed investigation creation payload */
export interface InvestigationCreate {
  scenario_id: EntityId;
  title?: string | null;
  description?: string | null;
  metadata?: JsonObject;
  /** Nested fault configuration (preferred over flat fault_type). */
  fault_config?: FaultConfig;
  agent_config?: AgentConfig;
  scoring_config?: ScoringConfig;
}

/** One ranked causal explanation */
export interface Hypothesis {
  hypothesis_id: EntityId;
  title: string;
  summary: string;
  causal_chain: string[];
  evidence_ids: EntityId[];
  contradiction_ids: EntityId[];
  assumptions: string[];
  confidence: number;
  score: number;
  metadata?: Record<string, any>;
}

export interface HypothesisListResponse {
  investigation_id: EntityId;
  hypotheses: Hypothesis[];
}

/** One reconstructed event in the investigation timeline */
export interface TimelineEvent {
  event_id: EntityId;
  timestamp: string; // ISO 8601 UTC
  subsystem: SubsystemId;
  event_type: TypeName;
  description: string;
  severity: Severity;
  metadata: JsonObject;
}

export interface TimelineResponse {
  investigation_id: EntityId;
  events: TimelineEvent[];
}

/* -------------------------------------------------------
   Fault injection
   ------------------------------------------------------- */

/** Fault configuration (POST /api/v1/scenarios/{id}/inject) */
export interface FaultConfig {
  fault_type: FaultType;
  target_subsystem: SubsystemId;
  start_time: string; // ISO 8601 UTC
  duration_seconds: number;
  magnitude: number;
  parameters?: JsonObject;
}

export interface InjectionPreview {
  injection_id: EntityId;
  scenario_id: EntityId;
  preview: boolean;
  applied: boolean;
  fault_config: FaultConfig;
  effective_start_time: string;
  effective_end_time: string;
  scenario: ScenarioDetailResponse;
}

/* -------------------------------------------------------
   Runs
   ------------------------------------------------------- */

export interface RunResponse {
  run_id: EntityId;
  scenario_id: EntityId;
  status: RunStatus;
  title: string;
  investigation_config: InvestigationConfig;
  fault_config: FaultConfig;
  queue_position: number;
  created_at: string;
  queued_at: string;
  message: string;
}

export interface InvestigationConfig {
  fault_config: FaultConfig;
  agent_config: AgentConfig;
  scoring_config: ScoringConfig;
}

export interface AgentConfig {
  enabled: boolean;
  max_hypotheses: number;
  temperature: number;
  model: string | null;
  seed: number | null;
  timeout_seconds: number;
  prompt_version: string | null;
}

export interface ScoringConfig {
  evidence_weight: number;
  consistency_weight: number;
  coverage_weight: number;
  contradiction_penalty: number;
}

/* -------------------------------------------------------
   Errors (RFC 9457 problem+json)
   ------------------------------------------------------- */

export interface ProblemError {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  code: string;
  request_id: string;
  errors?: ProblemError[];
}

/* -------------------------------------------------------
   Re-exported domain types for consumers
   ------------------------------------------------------- */

export type { EvaluationMetrics };
export type { Graph, GraphEdge, GraphNode };
