/* =============================================================================
   Evaluation Dashboard Page
   -------------------------------------------------------
   Displays run metrics, evaluation scores, and performance data across
   investigations. Shows root cause accuracy, runtime, evidence weighting,
   and contradiction penalties per investigation run.
   ============================================================================= */

import { useEffect, useState } from "react";
import {
  listInvestigations,
  getInvestigation,
} from "../../api/client";
import type {
  InvestigationSummary,
  InvestigationRead,
  EvaluationMetrics,
} from "../../types/api";

export function EvaluationDashboardPage() {
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [metricsByInv, setMetricsByInv] = useState<
    Record<string, EvaluationMetrics>
  >({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    listInvestigations(controller.signal)
      .then((data) => {
        setInvestigations(data);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Unknown error");
      });

    // For each investigation, fetch the full read to get evaluation metrics
    Promise.all(
      data.map((summary) =>
        getInvestigation(summary.investigation_id, controller.signal).then(
          (read) => {
            setMetricsByInv((prev) => ({
              ...prev,
              [read.investigation_id]: read.evaluation_metrics ?? {},
            }));
          }
        )
      )
    ).then(() => setLoading(false));

    return () => {
      controller.abort();
    };
  }, []);

  if (loading) {
    return (
      <section className="page evaluation-dashboard">
        <div className="page__loading">
          <p>Loading evaluation data...</p>
        </div>
      </section>
    );
  }

  return (
    <section className="page evaluation-dashboard">
      <div className="page__header">
        <h2 className="page__title">Evaluation Dashboard</h2>
        <p className="page__subtitle">
          Investigation run metrics and evaluation scores
        </p>
      </div>

      {error && (
        <div className="error-banner">
          <p>{error}</p>
        </div>
      )}

      {investigations.length === 0 && (
        <div className="empty-state">
          <p>No investigations found. Create or load an investigation to see metrics.</p>
        </div>
      )}

      <div className="metrics-table">
        <table>
          <thead>
            <tr>
              <th>Investigation</th>
              <th>Status</th>
              <th>Root Cause Accuracy</th>
              <th>Runtime (s)</th>
              <th>Evidence Weight</th>
              <th>Consistency Weight</th>
              <th>Coverage Weight</th>
              <th>Contradiction Penalty</th>
            </tr>
          </thead>
          <tbody>
            {investigations.map((summary) => {
              const metrics = metricsByInv[summary.investigation_id] || {};
              return (
                <tr key={summary.investigation_id}>
                  <td>
                    <strong>{summary.investigation_id}</strong>
                  </td>
                  <td>
                    <span
                      className={
                        summary.status === "completed"
                          ? "status--completed"
                          : summary.status === "failed"
                          ? "status--failed"
                          : "status--running"
                      }
                    >
                      {summary.status}
                    </span>
                  </td>
                  <td>{metrics.root_cause_accuracy?.toFixed(2) ?? "N/A"}</td>
                  <td>{metrics.runtime_seconds?.toFixed(1) ?? "N/A"}</td>
                  <td>{metrics.evidence_weight?.toFixed(2) ?? "N/A"}</td>
                  <td>{metrics.consistency_weight?.toFixed(2) ?? "N/A"}</td>
                  <td>{metrics.coverage_weight?.toFixed(2) ?? "N/A"}</td>
                  <td>{metrics.contradiction_penalty?.toFixed(2) ?? "N/A"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {investigations.length > 0 && (
        <div className="metrics-aggregates">
          <h3>Aggregates</h3>
          <dl>
            <div>
              <dt>Average root cause accuracy</dt>
              <dd>
                {Object.values(metricsByInv)
                  .filter((m) => m.root_cause_accuracy != null)
                  .reduce(
                    (sum, m) => sum + (m.root_cause_accuracy ?? 0),
                    0
                  ) /
                  Object.values(metricsByInv).filter((m) => m.root_cause_accuracy != null)
                    .length || "N/A"}</dd>
            </div>
            <div>
              <dt>Total investigations</dt>
              <dd>{investigations.length}</dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  );
}