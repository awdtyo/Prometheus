import { useCallback, useEffect, useState } from "react";

import type {
  ConnectionStatus,
  EvaluationMetrics,
  FaultConfig,
  HealthResponse,
  HypothesisListResponse,
  InjectionPreview,
  Investigation,
  InvestigationCreate,
  InvestigationListResponse,
  Problem,
  ScenarioDetailResponse,
  ScenarioListResponse,
  SubsystemListResponse,
  TimelineResponse,
} from "../types/api";

/* =============================================================================
   Vite env configuration
   ============================================================================= */

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/+$/, "");

export const API_DOCS_URL =
  import.meta.env.VITE_API_DOCS_URL?.trim() || "http://127.0.0.1:8000/docs";

export { apiBaseUrl };

/* =============================================================================
   Client errors
   ============================================================================= */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly body: Problem | null;

  constructor(status: number, code: string | null, body: Problem | null, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

/* =============================================================================
   Low-level request
   ============================================================================= */

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${apiBaseUrl}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });

  if (!res.ok) {
    let body: Problem | null = null;
    try {
      body = (await res.json()) as Problem;
    } catch {
      body = null;
    }
    const code = body?.code || String(res.status);
    const detail = body?.detail || res.statusText;
    throw new ApiError(res.status, code, body, detail);
  }

  if (res.status === 204 || res.status === 205) {
    return null as unknown as T;
  }

  return (await res.json()) as T;
}

function get<T>(path: string, signal?: AbortSignal): Promise<T> {
  return request<T>(path, { signal });
}

function post<Body, Response>(
  path: string,
  body: Body,
  signal?: AbortSignal,
): Promise<Response> {
  return request<Response>(path, {
    method: "POST",
    body: JSON.stringify(body),
    signal,
  });
}

/* =============================================================================
   Typed service functions
   ============================================================================= */

/** GET /api/v1/health */
export function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return get<HealthResponse>("/api/v1/health", signal);
}

/** GET /api/v1/scenarios */
export function listScenarios(signal?: AbortSignal): Promise<ScenarioListResponse> {
  return get<ScenarioListResponse>("/api/v1/scenarios", signal);
}

/** GET /api/v1/scenarios/{scenario_id} */
export function getScenario(
  scenarioId: string,
  signal?: AbortSignal,
): Promise<ScenarioDetailResponse> {
  return get<ScenarioDetailResponse>(
    `/api/v1/scenarios/${encodeURIComponent(scenarioId)}`,
    signal,
  );
}

/** GET /api/v1/subsystems */
export function listSubsystems(signal?: AbortSignal): Promise<SubsystemListResponse> {
  return get<SubsystemListResponse>("/api/v1/subsystems", signal);
}

/** GET /api/v1/investigations */
export function listInvestigations(
  limit?: number,
  cursor?: string | null,
  signal?: AbortSignal,
): Promise<InvestigationListResponse> {
  const params = new URLSearchParams();
  if (limit !== undefined) params.set("limit", String(limit));
  if (cursor) params.set("cursor", cursor);
  const qs = params.toString();
  return get<InvestigationListResponse>(
    `/api/v1/investigations${qs ? `?${qs}` : ""}`,
    signal,
  );
}

/** POST /api/v1/investigations */
export function createInvestigation(
  payload: InvestigationCreate,
  signal?: AbortSignal,
): Promise<Investigation> {
  return post<InvestigationCreate, Investigation>("/api/v1/investigations", payload, signal);
}

/** GET /api/v1/investigations/{investigation_id} */
export function getInvestigation(
  investigationId: string,
  signal?: AbortSignal,
): Promise<Investigation> {
  return get<Investigation>(
    `/api/v1/investigations/${encodeURIComponent(investigationId)}`,
    signal,
  );
}

/** GET /api/v1/investigations/{investigation_id}/hypotheses */
export function listHypotheses(
  investigationId: string,
  signal?: AbortSignal,
): Promise<HypothesisListResponse> {
  return get<HypothesisListResponse>(
    `/api/v1/investigations/${encodeURIComponent(investigationId)}/hypotheses`,
    signal,
  );
}

/** GET /api/v1/investigations/{investigation_id}/timeline */
export function getTimeline(
  investigationId: string,
  signal?: AbortSignal,
): Promise<TimelineResponse> {
  return get<TimelineResponse>(
    `/api/v1/investigations/${encodeURIComponent(investigationId)}/timeline`,
    signal,
  );
}

/** POST /api/v1/scenarios/{scenario_id}/inject */
export function injectFault(
  scenarioId: string,
  config: FaultConfig,
  signal?: AbortSignal,
): Promise<InjectionPreview> {
  return post<FaultConfig, InjectionPreview>(
    `/api/v1/scenarios/${encodeURIComponent(scenarioId)}/inject`,
    config,
    signal,
  );
}

/* =============================================================================
   React hook layer
   ============================================================================= */

function useApi<T>(
  execute: (signal: AbortSignal) => Promise<T>,
  deps: unknown[],
): { data: T | null; error: Error | null; isLoading: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;
    setIsLoading(true);
    execute(controller.signal)
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      })
      .catch((err) => {
        if (!cancelled && !controller.signal.aborted) {
          setError(err);
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, deps);

  return { data, error, isLoading };
}

export function useHealth() {
  return useApi<HealthResponse>((signal) => getHealth(signal), []);
}

export function useScenarios() {
  return useApi<ScenarioListResponse>((signal) => listScenarios(signal), []);
}

export function useScenario(scenarioId: string | null) {
  return useApi<ScenarioDetailResponse | null>(
    (signal) =>
      scenarioId ? getScenario(scenarioId, signal) : Promise.resolve(null),
    [scenarioId],
  );
}

export function useSubsystems() {
  return useApi<SubsystemListResponse>((signal) => listSubsystems(signal), []);
}

export function useInvestigations() {
  return useApi<InvestigationListResponse>(
    (signal) => listInvestigations(undefined, undefined, signal),
    [],
  );
}

export function useInvestigation(investigationId: string | null) {
  return useApi<Investigation | null>(
    (signal) =>
      investigationId ? getInvestigation(investigationId, signal) : Promise.resolve(null),
    [investigationId],
  );
}

export function useHypotheses(investigationId: string | null) {
  return useApi<HypothesisListResponse | null>(
    (signal) =>
      investigationId
        ? listHypotheses(investigationId, signal)
        : Promise.resolve(null),
    [investigationId],
  );
}

export function useTimeline(investigationId: string | null) {
  return useApi<TimelineResponse | null>(
    (signal) =>
      investigationId ? getTimeline(investigationId, signal) : Promise.resolve(null),
    [investigationId],
  );
}

export function useCreateInvestigation() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const create = useCallback(
    (payload: InvestigationCreate): Promise<Investigation> => {
      setIsLoading(true);
      setError(null);
      return createInvestigation(payload).then(
        (result) => {
          setIsLoading(false);
          return result;
        },
        (err) => {
          setIsLoading(false);
          setError(err);
          throw err;
        },
      );
    },
    [],
  );

  return { create, isLoading, error };
}

export function useInjectFault(scenarioId: string | null) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const inject = useCallback(
    (config: FaultConfig): Promise<InjectionPreview> => {
      if (!scenarioId) {
        const err = new Error("No scenario selected");
        setError(err);
        throw err;
      }
      setIsLoading(true);
      setError(null);
      return injectFault(scenarioId, config).then(
        (result) => {
          setIsLoading(false);
          return result;
        },
        (err) => {
          setIsLoading(false);
          setError(err);
          throw err;
        },
      );
    },
    [scenarioId],
  );

  return { inject, isLoading, error };
}

/* =============================================================================
   Convenience helpers
   ============================================================================= */

/** Empty 12-field EvaluationMetrics shape (mock backend exposes no metrics endpoint). */
export function emptyEvaluationMetrics(): EvaluationMetrics {
  return {
    root_cause_accuracy: 0,
    runtime_seconds: 0,
    evidence_weight: 0,
    consistency_weight: 0,
    coverage_weight: 0,
    contradiction_penalty: 0,
    fault_localization_accuracy: 0,
    causal_chain_accuracy: 0,
    evidence_coverage: 0,
    temporal_ordering_accuracy: 0,
    contradiction_handling: 0,
    unsupported_claim_rate: 0,
  };
}

export function problemFromError(error: unknown): {
  status: number;
  code: string | null;
  detail: string;
} {
  if (error instanceof ApiError) {
    return {
      status: error.status,
      code: error.code,
      detail: error.body?.detail || error.message,
    };
  }
  return {
    status: 0,
    code: null,
    detail: error instanceof Error ? error.message : String(error),
  };
}

export type { ConnectionStatus };
