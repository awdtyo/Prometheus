import type {
  HealthResponse,
  ConnectionStatus,
  InvestigationSummary,
  HypothesisSummary,
  TimelineEvent,
  InvestigationCreate,
  FaultConfigCreate,
  AgentConfigCreate,
  ScoringConfigCreate,
  InvestigationRead,
  ScenarioSummary,
  ObservationSummary,
  EvaluationMetrics,
  BaselineComparison,
  ScenarioPerformance,
  ErrorBreakdown,
  HypothesisRankingComparison,
  MockInvestigation,
  MockScenario,
  MockObservation,
  MockGraph,
  MockGraphNode,
  MockGraphEdge,
  MockHypothesis,
  EntityId,
  SubsystemId,
  TypeName,
  Severity,
  RunStatus,
  FaultType,
  RelationshipType,
  JsonObject,
} from "./types/api";

/* =============================================================================
   Vite env configuration
   ============================================================================= */

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/+$/, "");

export const API_DOCS_URL =
  import.meta.env.VITE_API_DOCS_URL?.trim() || "http://127.0.0.1:8000/docs";

export const VITE_API_BASE_URL = configuredBaseUrl || "http://127.0.0.1:8000";

/* =============================================================================
   Mock data fixtures (stand-in for backend responses)
   These are pure data, independent of any UI component.
   ============================================================================= */

const MOCK_SCENARIOS: MockScenario[] = [
  {
    scenario_id: "scn_001",
    name: "Power System Undervoltage Event",
    description: "A sequence of undervoltage events leading to bus undervoltage and spacecraft power loss",
    mission_start_utc: "2026-10-30T12:00:00Z",
    subsystems: ["power", "thermal-control", "propulsion"],
  },
  {
    scenario_id: "scn_002",
    name: "Thermal Overheat Scenario",
    description: "Thermal control subsystem failure causing gradual temperature rise",
    mission_start_utc: "2026-10-30T12:00:00Z",
    subsystems: ["thermal-control", "power", "battery"],
  },
];

const MOCK_INVESTIGATIONS: MockInvestigation[] = [
  {
    investigation_id: "inv_001",
    scenario_id: "scn_001",
    status: "completed",
    created_at: "2026-10-30T12:00:00Z",
    updated_at: "2026-10-30T12:02:00Z",
    scenario: MOCK_SCENARIOS[0],
    run_timestamps: {
      created_at: "2026-10-30T12:00:00Z",
      started_at: "2026-10-30T12:00:01Z",
      completed_at: "2026-10-30T12:02:00Z",
    },
    observations: [
      {
        observation_id: "obs_001",
        timestamp: "2026-10-30T12:00:30Z",
        subsystem: "power",
        observation_type: "threshold_breach",
        description: "Bus voltage fell below the 26 V limit for 30 seconds.",
        observed_value: 25.4,
        threshold: 26.0,
        severity: "high",
        source_ids: ["evt_001", "tel:bus-1"],
      },
      {
        observation_id: "obs_002",
        timestamp: "2026-10-30T12:01:15Z",
        subsystem: "power",
        observation_type: "undervoltage",
        description: "Bus voltage continued to decay toward 24 V.",
        observed_value: 24.1,
        threshold: null,
        severity: "critical",
        source_ids: ["evt_002"],
      },
    ],
    graph: {
      nodes: [
        {
          node_id: "sub:power",
          node_type: "subsystem",
          label: "Power",
          timestamp: "2026-10-30T12:00:00Z",
          metadata: { critical: true },
        },
        {
          node_id: "obs_001",
          node_type: "observation",
          label: "Undervoltage",
          timestamp: "2026-10-30T12:00:30Z",
          metadata: {},
        },
        {
          node_id: "obs_002",
          node_type: "observation",
          label: "Continued Decay",
          timestamp: "2026-10-30T12:01:15Z",
          metadata: {},
        },
        {
          node_id: "evt_001",
          node_type: "event",
          label: "Under-voltage alert",
          timestamp: "2026-10-30T12:00:30Z",
          metadata: {},
        },
        {
          node_id: "evt_002",
          node_type: "event",
          label: "Voltage decay alert",
          timestamp: "2026-10-30T12:01:15Z",
          metadata: {},
        },
      ],
      edges: [
        {
          edge_id: "edg_001",
          source: "sub:power",
          target: "obs_001",
          relationship_type: "TEMPORAL_PRECEDENCE",
          evidence_ids: ["ev_001"],
          confidence: 0.95,
          metadata: { note: "power precedes the observation" },
        },
        {
          edge_id: "edg_002",
          source: "sub:power",
          target: "obs_002",
          relationship_type: "TEMPORAL_PRECEDENCE",
          evidence_ids: ["ev_002"],
          confidence: 0.88,
          metadata: { note: "power precedes the continued decay" },
        },
        {
          edge_id: "edg_003",
          source: "obs_001",
          target: "obs_002",
          relationship_type: "TEMPORAL_PRECEDENCE",
          evidence_ids: [],
          confidence: 0.91,
          metadata: { note: "undervoltage preceded continued decay" },
        },
      ],
    },
    hypotheses: [
      {
        hypothesis_id: "hyp_001",
        title: "Battery heater fault caused bus undervoltage",
        summary: "A stuck heater drained the battery and caused the bus voltage to sag.",
        causal_chain: [
          "Heater stuck on",
          "Battery depleted",
          "Bus voltage fell",
        ],
        evidence_ids: ["ev_001"],
        contradiction_ids: [],
        assumptions: [
          "Battery state of health was nominal before the fault",
        ],
        confidence: 0.82,
        score: 0.79,
      },
      {
        hypothesis_id: "hyp_002",
        title: "Power distribution unit failure caused undervoltage",
        summary: "A partial failure in the power distribution unit reduced output capacity.",
        causal_chain: [
          "PDU output degraded",
          "Bus voltage sagged",
          "Loads shed to manage margin",
        ],
        evidence_ids: ["ev_002"],
        contradiction_ids: ["hyp_001"],
        assumptions: [
          "Heater was functioning nominally before PDU failure",
        ],
        confidence: 0.67,
        score: 0.62,
      },
    ],
    investigation_report: "# Investigation Report\n\n## Summary\nThe investigation concluded that a stuck battery heater was the primary cause of the bus undervoltage event, leading to cascading power management actions.\n\n## Causal Chain\n1. Heater stuck on\n2. Battery depletion\n3. Bus voltage fell below safe limits\n\n## Recommendations\n- Review heater control logic for stuck-on failure modes\n- Add redundant heating circuit for future missions\n- Update battery management thresholds",
    evaluation_metrics: {
      root_cause_accuracy: 1.0,
      runtime_seconds: 124.5,
      evidence_weight: 0.4,
      consistency_weight: 0.35,
      coverage_weight: 0.25,
      contradiction_penalty: 0.2,
    },
  },
];

/* =============================================================================
   API service mock implementations
   Each function independently returns mock data; none hardcode state into
   other functions. This lets the UI call any endpoint without ordering
   requirements.
   ============================================================================= */

/** GET /api/health */
export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  // Simulate network latency
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  return {
    status: "ok",
    service: "Mission Autopsy API",
    version: "0.1.0",
    environment: "development",
  };
}

/** GET /api/scenarios */
export async function listScenarios(signal?: AbortSignal): Promise<MockScenario[]> {
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  return [...MOCK_SCENARIOS];
}

/** GET /api/investigations */
export async function listInvestigations(signal?: AbortSignal): Promise<InvestigationSummary[]> {
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  return MOCK_INVESTIGATIONS.map((inv) => ({
    investigation_id: inv.investigation_id,
    scenario_id: inv.scenario_id,
    status: inv.status,
    created_at: inv.created_at,
    updated_at: inv.updated_at,
  }));
}

/** GET /api/investigations/{investigation_id} */
export async function getInvestigation(
  investigationId: EntityId,
  signal?: AbortSignal,
): Promise<InvestigationRead> {
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  const inv = MOCK_INVESTIGATIONS.find((i) => i.investigation_id === investigationId);

  if (!inv) {
    throw new Error(`Investigation ${investigationId} not found`);
  }

  // Map mock data to API response shape
  return {
    investigation_id: inv.investigation_id,
    scenario_id: inv.scenario_id,
    status: inv.status,
    created_at: inv.created_at,
    updated_at: inv.updated_at,
    scenario: {
      scenario_id: inv.scenario.scenario_id,
      name: inv.scenario.name,
      description: inv.scenario.description,
      mission_start_utc: inv.scenario.mission_start_utc,
      subsystems: inv.scenario.subsystems,
    },
    run_timestamps: inv.run_timestamps,
    observations: inv.observations.map((obs) => ({
      observation_id: obs.observation_id,
      timestamp: obs.timestamp,
      subsystem: obs.subsystem,
      observation_type: obs.observation_type,
      description: obs.description,
      observed_value: obs.observed_value,
      threshold: obs.threshold,
      severity: obs.severity,
      source_ids: obs.source_ids,
    })),
    graph: {
      nodes: inv.graph.nodes.map((node) => ({
        node_id: node.node_id,
        node_type: node.node_type,
        label: node.label,
        timestamp: node.timestamp,
        metadata: node.metadata,
      })),
      edges: inv.graph.edges.map((edge) => ({
        edge_id: edge.edge_id,
        source: edge.source,
        target: edge.target,
        relationship_type: edge.relationship_type,
        evidence_ids: edge.evidence_ids,
        confidence: edge.confidence,
        metadata: edge.metadata,
      })),
    },
    hypotheses: inv.hypotheses.map((hyp) => ({
      hypothesis_id: hyp.hypothesis_id,
      title: hyp.title,
      summary: hyp.summary,
      causal_chain: hyp.causal_chain,
      evidence_ids: hyp.evidence_ids,
      contradiction_ids: hyp.contradiction_ids,
      assumptions: hyp.assumptions,
      confidence: hyp.confidence,
      score: hyp.score,
      status: inv.status,
    })),
    investigation_report: inv.investigation_report,
    evaluation_metrics: inv.evaluation_metrics,
  };
}

/** GET /api/investigations/{investigation_id}/hypotheses */
export async function listHypotheses(
  investigationId: EntityId,
  signal?: AbortSignal,
): Promise<HypothesisSummary[]> {
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  const inv = MOCK_INVESTIGATIONS.find((i) => i.investigation_id === investigationId);

  if (!inv) {
    throw new Error(`Investigation ${investigationId} not found`);
  }

  return inv.hypotheses.map((hyp) => ({
    hypothesis_id: hyp.hypothesis_id,
    title: hyp.title,
    summary: hyp.summary,
    confidence: hyp.confidence,
    score: hyp.score,
    status: inv.status,
  }));
}

/** GET /api/investigations/{investigation_id}/evaluation-metrics */
export async function getEvaluationMetrics(
  investigationId: EntityId,
  signal?: AbortSignal,
): Promise<EvaluationMetrics> {
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  const inv = MOCK_INVESTIGATIONS.find((i) => i.investigation_id === investigationId);

  if (!inv) {
    throw new Error(`Investigation ${investigationId} not found`);
  }

  return {
    root_cause_accuracy: inv.evaluation_metrics?.root_cause_accuracy ?? 1.0,
    runtime_seconds: inv.evaluation_metrics?.runtime_seconds ?? 124.5,
    evidence_weight: inv.evaluation_metrics?.evidence_weight ?? 0.4,
    consistency_weight: inv.evaluation_metrics?.consistency_weight ?? 0.35,
    coverage_weight: inv.evaluation_metrics?.coverage_weight ?? 0.25,
    contradiction_penalty: inv.evaluation_metrics?.contradiction_penalty ?? 0.2,
    fault_localization_accuracy: 0.85,
    causal_chain_accuracy: 0.78,
    evidence_coverage: 0.72,
    temporal_ordering_accuracy: 0.81,
    contradiction_handling: 0.74,
    unsupported_claim_rate: 0.12,
  };
}

/** GET /api/investigations/{investigation_id}/baseline-comparison */
export async function getBaselineComparison(
  investigationId: EntityId,
  signal?: AbortSignal,
): Promise<BaselineComparison> {
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  const inv = MOCK_INVESTIGATIONS.find((i) => i.investigation_id === investigationId);

  if (!inv) {
    throw new Error(`Investigation ${investigationId} not found`);
  }

  // Use the existing evaluation metrics to derive baseline comparisons
  const metrics = inv.evaluation_metrics;
  return {
    threshold_only: metrics?.fault_localization_accuracy ?? 0.65,
    earliest_anomaly: metrics?.causal_chain_accuracy ?? 0.70,
    dependency_only: metrics?.evidence_coverage ?? 0.70,
    full_autopsy: 0.88, // Mission Autopsy overall performance
  };
}

/** GET /api/investigations/{investigation_id}/scenario-performance */
export async function getScenarioPerformance(
  investigationId: EntityId,
  signal?: AbortSignal,
): Promise<ScenarioPerformance[]> {
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  const inv = MOCK_INVESTIGATIONS.find((i) => i.investigation_id === investigationId);

  if (!inv) {
    throw new Error(`Investigation ${investigationId} not found`);
  }

  const scenarioId = inv.scenario_id;
  // Return performance data for scenarios associated with this investigation
  return [
    {
      scenario_id: scenarioId,
      scenario_name: inv.scenario?.name || "Unknown Scenario",
      fault_localization: 0.85,
      causal_accuracy: 0.78,
      evidence_cov: 0.72,
      temporal_accuracy: 0.81,
      contradiction_score: 0.74,
      unsupported_rate: 0.12,
    },
  ];
}

/** GET /api/investigations/{investigation_id}/error-breakdown */
export async function getErrorBreakdown(
  investigationId: EntityId,
  signal?: AbortSignal,
): Promise<ErrorBreakdown> {
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  const inv = MOCK_INVESTIGATIONS.find((i) => i.investigation_id === investigationId);

  if (!inv) {
    throw new Error(`Investigation ${investigationId} not found`);
  }

  return {
    mislocalized_faults: 3,
    chain_errors: 2,
    temporal_errors: 1,
    unsupported_claims: 2,
    total_evidence: inv.observations?.length || 2,
  };
}

/** GET /api/investigations/{investigation_id}/hypothesis-ranking-comparison */
export async function getHypothesisRankingComparison(
  investigationId: EntityId,
  signal?: AbortSignal,
): Promise<HypothesisRankingComparison[]> {
  await new Promise((resolve) => setTimeout(resolve, 300));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  const inv = MOCK_INVESTIGATIONS.find((i) => i.investigation_id === investigationId);

  if (!inv) {
    throw new Error(`Investigation ${investigationId} not found`);
  }

  return inv.hypotheses.map((hyp) => ({
    hypothesis_id: hyp.hypothesis_id,
    title: hyp.title,
    rank: hyp.evidence_ids?.length > 0 ? 1 : 3, // Simple ranking based on evidence
    score: hyp.score,
    causal_acc: hyp.confidence,
    evidence_count: hyp.evidence_ids?.length || 0,
    contradiction_count: hyp.contradiction_ids?.length || 0,
    assumptions_count: hyp.assumptions?.length || 0,
  }));
}

/** POST /api/investigations */
export async function createInvestigation(
  payload: InvestigationCreate,
  signal?: AbortSignal,
): Promise<InvestigationRead> {
  await new Promise((resolve) => setTimeout(resolve, 500));

  if (signal?.aborted) {
    throw new Error("Aborted");
  }

  // Create a new investigation from the payload using mock data
  const scenario = MOCK_SCENARIOS[0]; // In real use, resolve by scenario_id

  const newInvestigation: MockInvestigation = {
    investigation_id: `inv_${String(MOCK_INVESTIGATIONS.length + 1).padStart(3, "0")}`,
    scenario_id: payload.scenario_id,
    status: "pending",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    scenario: scenario,
    run_timestamps: {
      created_at: new Date().toISOString(),
    },
    observations: [],
    graph: { nodes: [], edges: [] },
    hypotheses: [],
    evaluation_metrics: {
      root_cause_accuracy: 0,
      runtime_seconds: 0,
      evidence_weight: payload.scoring_config?.evidence_weight ?? 0.4,
      consistency_weight: payload.scoring_config?.consistency_weight ?? 0.35,
      coverage_weight: payload.scoring_config?.coverage_weight ?? 0.25,
      contradiction_penalty: payload.scoring_config?.contradiction_penalty ?? 0.2,
    },
  };

  // Store it (in-memory only for mock)
  ;(global as any).mockInvestigations = (global as any).mockInvestigations || [];
  ;(global as any).mockInvestigations.push(newInvestigation);

  return {
    investigation_id: newInvestigation.investigation_id,
    scenario_id: newInvestigation.scenario_id,
    status: newInvestigation.status,
    created_at: newInvestigation.created_at,
    updated_at: newInvestigation.updated_at,
    scenario: {
      scenario_id: newInvestigation.scenario.scenario_id,
      name: newInvestigation.scenario.name,
      description: newInvestigation.scenario.description,
      mission_start_utc: newInvestigation.scenario.mission_start_utc,
      subsystems: newInvestigation.scenario.subsystems,
    },
    run_timestamps: newInvestigation.run_timestamps,
    observations: newInvestigation.observations.map((obs) => ({
      observation_id: obs.observation_id,
      timestamp: obs.timestamp,
      subsystem: obs.subsystem,
      observation_type: obs.observation_type,
      description: obs.description,
      observed_value: obs.observed_value,
      threshold: obs.threshold,
      severity: obs.severity,
      source_ids: obs.source_ids,
    })),
    graph: {
      nodes: newInvestigation.graph.nodes.map((node) => ({
        node_id: node.node_id,
        node_type: node.node_type,
        label: node.label,
        timestamp: node.timestamp,
        metadata: node.metadata,
      })),
      edges: newInvestigation.graph.edges.map((edge) => ({
        edge_id: edge.edge_id,
        source: edge.source,
        target: edge.target,
        relationship_type: edge.relationship_type,
        evidence_ids: edge.evidence_ids,
        confidence: edge.confidence,
        metadata: edge.metadata,
      })),
    },
    hypotheses: newInvestigation.hypotheses.map((hyp) => ({
      hypothesis_id: hyp.hypothesis_id,
      title: hyp.title,
      summary: hyp.summary,
      causal_chain: hyp.causal_chain,
      evidence_ids: hyp.evidence_ids,
      contradiction_ids: hyp.contradiction_ids,
      assumptions: hyp.assumptions,
      confidence: hyp.confidence,
      score: hyp.score,
      status: newInvestigation.status,
    })),
    investigation_report: newInvestigation.investigation_report,
    evaluation_metrics: newInvestigation.evaluation_metrics,
  };
}

/* ---------------------------------------------------------------------------
   Export types for consumers who need the full shape without hitting the API
   --------------------------------------------------------------------------- */

export type {
  MockScenario,
  MockInvestigation,
  MockObservation,
  MockGraph,
  MockGraphNode,
  MockGraphEdge,
  MockHypothesis,
};