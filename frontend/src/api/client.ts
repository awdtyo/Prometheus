import type { HealthResponse } from "../types/api";

const configuredBaseUrl = import.meta.env.VITE_API_BASE_URL?.trim();
const apiBaseUrl = (configuredBaseUrl || "/api").replace(/\/+$/, "");

export const API_DOCS_URL =
  import.meta.env.VITE_API_DOCS_URL?.trim() || "http://127.0.0.1:8000/docs";

/**
 * Fetch backend liveness metadata. The frontend never calls domain logic
 * directly; every interaction goes through the HTTP API.
 */
export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${apiBaseUrl}/health`, {
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}.`);
  }

  return (await response.json()) as HealthResponse;
}
