import { EntityId, SubsystemId, ParameterName, TypeName, Severity, RunStatus, EvidenceType, EvidenceStance, FaultType, NodeType, RelationshipType, JsonObject } from "./domain";

export type ConnectionStatus = "loading" | "online" | "offline";

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
}

/* =============================================================================
   Planned API DTO types (mirroring docs/api-contract.md)
   ============================================================================= */

/** Investigation summary returned by list/get endpoints */
export interface InvestigationSummary {
  investigation_id: EntityId;
  scenario_id: EntityId;
  status: RunStatus;
  created_at: string; // ISO 8601 UTC
  updated_at: string; // ISO 8601 UTC
}

/** Hypothesis summary returned by list endpoint */
export interface HypothesisSummary {
  hypothesis_id: EntityId;
  title: string;
  summary: string;
  confidence: number;
  score: number;
  status: RunStatus;
}

/** Timeline event item */
export interface TimelineEvent {
  event_id: EntityId;
  timestamp: string; // ISO 8601 UTC
  subsystem: SubsystemId;
  event_type: TypeName;
  description: string;
  severity: Severity;
}

/** Proposed investigation creation payload */
export interface InvestigationCreate {
  scenario_id: EntityId;
  fault_config: FaultConfigCreate;
  agent_config?: AgentConfigCreate;
  scoring_config?: ScoringConfigCreate;
}

/** Fault config for API creation */
export interface FaultConfigCreate {
  fault_type: FaultType;
  target_subsystem: SubsystemId;
  start_time: string; // ISO 8601 UTC
  duration_seconds: number;
  magnitude: number;
  parameters?: JsonObject;
}

/** Agent config for API creation */
export interface AgentConfigCreate {
  enabled?: boolean;
  max_hypotheses?: number;
  temperature?: number;
  model?: string;
  seed?: number;
  timeout_seconds?: number;
  prompt_version?: string;
}

/** Scoring config for API creation */
export interface ScoringConfigCreate {
  evidence_weight: number;
  consistency_weight: number;
  coverage_weight: number;
  contradiction_penalty: number;
}

/** Full investigation read response */
export interface InvestigationRead {
  investigation_id: EntityId;
  scenario_id: EntityId;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  scenario?: ScenarioSummary;
  run_timestamps: RunTimestamps;
  observations: ObservationSummary[];
  graph: GraphSummary;
  hypotheses: HypothesisSummary[];
  investigation_report?: string;
  evaluation_metrics?: EvaluationMetrics;
}

/** Summary of a scenario config */
export interface ScenarioSummary {
  scenario_id: EntityId;
  name: string;
  description: string;
  subsystem: SubsystemId;
}

/** Summary of an observation */
export interface ObservationSummary {
  observation_id: EntityId;
  timestamp: string;
  subsystem: SubsystemId;
  observation_type: TypeName;
  description: string;
  observed_value: number;
  threshold?: number;
  severity: Severity;
}

/** Evaluation metrics for an investigation */
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

/** Baseline comparison results */
export interface BaselineComparison {
  threshold_only: number;
  earliest_anomaly: number;
  dependency_only: number;
  full_autopsy: number;
}

/** Per-scenario performance */
export interface ScenarioPerformance {
  scenario_id: string;
  scenario_name: string;
  fault_localization: number;
  causal_accuracy: number;
  evidence_cov: number;
  temporal_accuracy: number;
  contradiction_score: number;
  unsupported_rate: number;
}

/** Error breakdown */
export interface ErrorBreakdown {
  mislocalized_faults: number;
  chain_errors: number;
  temporal_errors: number;
  unsupported_claims: number;
  total_evidence: number;
}

/** Hypothesis ranking comparison */
export interface HypothesisRankingComparison {
  hypothesis_id: string;
  title: string;
  rank: number;
  score: number;
  causal_acc: number;
  evidence_count: number;
  contradiction_count: number;
  assumptions_count: number;
}

/* =============================================================================
   Mock fixture types (internal, not sent over HTTP)
   ============================================================================= */

export interface MockInvestigation {
  investigation_id: EntityId;
  scenario_id: EntityId;
  status: RunStatus;
  created_at: string;
  updated_at: string;
  scenario: MockScenario;
  run_timestamps: RunTimestamps;
  observations: MockObservation[];
  graph: MockGraph;
  hypotheses: MockHypothesis[];
  investigation_report?: string;
  evaluation_metrics?: EvaluationMetrics;
}

export interface MockScenario {
  scenario_id: EntityId;
  name: string;
  description: string;
  mission_start_utc: string;
  subsystems: SubsystemId[];
}

export interface MockObservation {
  observation_id: EntityId;
  timestamp: string;
  subsystem: SubsystemId;
  observation_type: TypeName;
  description: string;
  observed_value: number;
  threshold?: number;
  severity: Severity;
  source_ids: EntityId[];
}

export interface MockGraph {
  nodes: MockGraphNode[];
  edges: MockGraphEdge[];
}

export interface MockGraphNode {
  node_id: EntityId;
  node_type: NodeType;
  label: string;
  timestamp?: string;
  metadata: JsonObject;
}

export interface MockGraphEdge {
  edge_id: EntityId;
  source: EntityId;
  target: EntityId;
  relationship_type: RelationshipType;
  evidence_ids: EntityId[];
  confidence: number;
  metadata: JsonObject;
}

export interface MockHypothesis {
  hypothesis_id: EntityId;
  title: string;
  summary: string;
  causal_chain: string[];
  evidence_ids: EntityId[];
  contradiction_ids: EntityId[];
  assumptions: string[];
  confidence: number;
  score: number;
}
