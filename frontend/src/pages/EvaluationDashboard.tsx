/* =============================================================================
   Evaluation Dashboard Page
   -------------------------------------------------------
   Displays comprehensive evaluation metrics, baseline comparisons, and
   performance data across investigations.
   ============================================================================= */

import { useEffect, useState } from "react";
import {
  listInvestigations,
  getInvestigation,
  getEvaluationMetrics,
  getBaselineComparison,
  getScenarioPerformance,
  getErrorBreakdown,
  getHypothesisRankingComparison,
} from "../../api/client";
import type {
  InvestigationSummary,
  InvestigationRead,
  EvaluationMetrics,
  BaselineComparison,
  ScenarioPerformance,
  ErrorBreakdown,
  HypothesisRankingComparison,
} from "../../types/api";

export function EvaluationDashboardPage() {
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [metricsByInv, setMetricsByInv] = useState<
    Record<string, EvaluationMetrics>
  >({});
  const [baselineComparisons, setBaselineComparisons] = useState<
    Record<string, BaselineComparison>
  >({});
  const [scenarioPerformance, setScenarioPerformance] = useState<
    Record<string, ScenarioPerformance[]>
  >({});
  const [errorBreakdowns, setErrorBreakdowns] = useState<
    Record<string, ErrorBreakdown>
  >({});
  const [hypothesisComparisons, setHypothesisComparisons] = useState<
    Record<string, HypothesisRankingComparison[]>
  >({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    // Parallel: load investigations and all associated data
    Promise.all([
      // 1. List investigations
      listInvestigations(controller.signal).then((data) => setInvestigations(data)),

      // 2. For each investigation, fetch full read + evaluation metrics + related data
      Promise.all(
        data.map((summary) =>
          Promise.all([
            // Get full investigation read
            getInvestigation(summary.investigation_id, controller.signal).then(
              (read) => ({
                summary,
                read,
              })
            ),
            // Get evaluation metrics
            getEvaluationMetrics(summary.investigation_id, controller.signal).then(
              (metrics) => ({
                summary,
                metrics,
              })
            ),
            // Get baseline comparison
            getBaselineComparison(summary.investigation_id, controller.signal).then(
              (comparison) => ({
                summary,
                comparison,
              })
            ),
            // Get scenario performance
            getScenarioPerformance(summary.investigation_id, controller.signal).then(
              (performance) => ({
                summary,
                performance,
              })
            ),
            // Get error breakdown
            getErrorBreakdown(summary.investigation_id, controller.signal).then(
              (breakdown) => ({
                summary,
                breakdown,
              })
            ),
            // Get hypothesis ranking comparison
            getHypothesisRankingComparison(summary.investigation_id, controller.signal).then(
              (comparisons) => ({
                summary,
                comparisons,
              })
            ),
          ])
        ))
      )
        .then((results) => {
          // Process all the data
          const newMetricsByInv: Record<string, EvaluationMetrics> = {};
          const newBaselineComparisons: Record<string, BaselineComparison> = {};
          const newScenarioPerformance: Record<string, ScenarioPerformance[]> = {};
          const newErrorBreakdowns: Record<string, ErrorBreakdown> = {};
          const newHypothesisComparisons: Record<string, HypothesisRankingComparison[]> = {};

          results.forEach((resultSet) => {
            const summary = resultSet[0].summary;
            const invId = summary.investigation_id;

            // Process evaluation metrics
            if (resultSet[1].metrics) {
              newMetricsByInv[invId] = {
                root_cause_accuracy: resultSet[1].metrics.root_cause_accuracy,
                runtime_seconds: resultSet[1].metrics.runtime_seconds,
                evidence_weight: resultSet[1].metrics.evidence_weight,
                consistency_weight: resultSet[1].metrics.consistency_weight,
                coverage_weight: resultSet[1].metrics.coverage_weight,
                contradiction_penalty: resultSet[1].metrics.contradiction_penalty,
                fault_localization_accuracy: resultSet[1].metrics.fault_localization_accuracy,
                causal_chain_accuracy: resultSet[1].metrics.causal_chain_accuracy,
                evidence_coverage: resultSet[1].metrics.evidence_coverage,
                temporal_ordering_accuracy: resultSet[1].metrics.temporal_ordering_accuracy,
                contradiction_handling: resultSet[1].metrics.contradiction_handling,
                unsupported_claim_rate: resultSet[1].metrics.unsupported_claim_rate,
              };
            }

            // Process baseline comparison
            if (resultSet[2].comparison) {
              newBaselineComparisons[invId] = {
                threshold_only: resultSet[2].comparison.threshold_only,
                earliest_anomaly: resultSet[2].comparison.earliest_anomaly,
                dependency_only: resultSet[2].comparison.dependency_only,
                full_autopsy: resultSet[2].comparison.full_autopsy,
              };
            }

            // Process scenario performance
            if (resultSet[3].performance) {
              if (!newScenarioPerformance[invId]) {
                newScenarioPerformance[invId] = [];
              }
              newScenarioPerformance[invId].push({
                scenario_id: resultSet[3].performance[0]?.scenario_id || invId,
                scenario_name: resultSet[3].performance[0]?.scenario_name || "Unknown Scenario",
                fault_localization: resultSet[3].performance[0]?.fault_localization,
                causal_accuracy: resultSet[3].performance[0]?.causal_accuracy,
                evidence_cov: resultSet[3].performance[0]?.evidence_cov,
                temporal_accuracy: resultSet[3].performance[0]?.temporal_accuracy,
                contradiction_score: resultSet[3].performance[0]?.contradiction_score,
                unsupported_rate: resultSet[3].performance[0]?.unsupported_rate,
              });
            }

            // Process error breakdown
            if (resultSet[4].breakdown) {
              newErrorBreakdowns[invId] = {
                mislocalized_faults: resultSet[4].breakdown.mislocalized_faults,
                chain_errors: resultSet[4].breakdown.chain_errors,
                temporal_errors: resultSet[4].breakdown.temporal_errors,
                unsupported_claims: resultSet[4].breakdown.unsupported_claims,
                total_evidence: resultSet[4].breakdown.total_evidence,
              };
            }

            // Process hypothesis ranking comparison
            if (resultSet[5].comparisons) {
              newHypothesisComparisons[invId] = resultSet[5].comparisons;
            }
          });

          setMetricsByInv(newMetricsByInv);
          setBaselineComparisons(newBaselineComparisons);
          setScenarioPerformance(newScenarioPerformance);
          setErrorBreakdowns(newErrorBreakdowns);
          setHypothesisComparisons(newHypothesisComparisons);
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Unknown error");
        })
        .finally(() => setLoading(false));
    return () => {
      controller.abort();
    };
  }, []);

  // Compute aggregates
  const avgRootCauseAccuracy = investigations.length > 0
    ? Object.values(metricsByInv)
        .filter((m) => m.root_cause_accuracy != null)
        .reduce((sum, m) => sum + (m.root_cause_accuracy ?? 0), 0) /
        Object.values(metricsByInv).filter((m) => m.root_cause_accuracy != null).length
    : null;

  // Compute baseline comparison aggregates
  const baselineValues = Object.values(baseline comparisons).reduce(
    (acc, m) => ({
      threshold_only: acc.threshold_only + m.threshold_only,
      earliest_anomaly: acc.earliest_anomaly + m.earliest_anomaly,
      dependency_only: acc.dependency_only + m.dependency_only,
      full_autopsy: acc.full_autopsy + m.full_autopsy,
    }),
    { threshold_only: 0, earliest_anomaly: 0, dependency_only: 0, full_autopsy: 0 }
  );
  const baselineCount = investigations.length || 1;
  const avgBaseline = {
    threshold_only: baselineValues.threshold_only / baselineCount,
    earliest_anomaly: baselineMetrics.earliest_anomaly / baselineCount,
    dependency_only: baselineMetrics.dependency_only / baselineCount,
    full_autopsy: baselineMetrics.full_autopsy / baselineCount,
  };

  // Compute hypothesis ranking aggregates
  const allRankings = Object.values(hypothesis comparisons)
    .flat()
    .sort((a, b) => a.rank - b.rank);

  const totalRankings = allRankings.length;
  const avgScore = totalRankings > 0
    ? allRankings.reduce((sum, r) => sum + r.score, 0) / totalRankings
    : 0;
  const avgCausalAcc = totalRankings > 0
    ? allRankings.reduce((sum, r) => sum + r.causal_acc, 0) / totalRankings
    : 0;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (loading) {
    return (
      <section className="page evaluation-dashboard">
        <div className="page__loading">
          <p>Loading evaluation data...</p>
        </div>
      </section>
    );
  }

  if (!investigations.length && Object.keys(metricsByInv).length === 0) {
    return (
      <section className="page evaluation-dashboard">
        <div className="page__empty">
          <p>No investigations found. Create or load an investigation to see metrics.</p>
          <button className="button button--primary" onClick={() => window.location.hash = "#workspace"}>
            Create Investigation
          </button>
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

      {/* Metrics Cards Section */}
      <div className="metrics-cards">
        <div className="metrics-cards-grid">
          {/* Root Cause Accuracy Card */}
          <div className="metric-card">
            <div className="metric-card__header">
              <strong>Root Cause Accuracy</strong>
              <span className="metric-card__value">
                {avgRootCauseAccuracy != null ? avgRootCauseAccuracy.toFixed(2) : "—"}
              </span>
            </div>
            <div className="metric-card__description">
              Across {investigations.length} investigations
            </div>
          </div>

          {/* Baseline Comparison Card */}
          <div className="metric-card">
            <div className="metric-card__header">
              <strong>Baseline Comparison</strong>
            </div>
            <div className="metric-card__body">
              <div className="baseline-item">
                <span>Full Autopsy</span>
                <span>{avgBaseline.full_autopsy.toFixed(2)}</span>
              </div>
              <div className="baseline-item">
                <span>Dependency Only</span>
                <span>{avgBaseline.dependency_only.toFixed(2)}</span>
              </div>
              <div className="baseline-item">
                <span>Earliest Anomaly</span>
                <span>{avgBaseline.earliest_anomaly.toFixed(2)}</span>
              </div>
              <div className="baseline-item">
                <span>Threshold Only</span>
                <span>{avgBaseline.threshold_only.toFixed(2)}</span>
              </div>
            </div>
          </div>

          {/* Evidence Coverage Card */}
          <div className="metric-card">
            <div className="metric-card__header">
              <strong>Evidence Coverage</strong>
              <span className="metric-card__value">
                {Object.values(metricsByInv)
                  .filter((m) => m.evidence_coverage != null)
                  .reduce((sum, m) => sum + m.evidence_coverage, 0) /
                  Object.values(metricsByInv).filter((m) => m.evidence_coverage != null).length || 0
                  .toFixed(2)}
              </span>
            </div>
            <div className="metric-card__description">
              Average across investigations
            </div>
          </div>

          {/* Hypothesis Ranking Card */}
          <div className="metric-card">
            <div className="metric-card__header">
              <strong>Hypothesis Ranking</strong>
            </div>
            <div className="metric-card__body">
              <strong>Average Score:</strong> {avgScore.toFixed(2)}
              <br/>
              <strong>Average Causal Accuracy:</strong> {avgCausalAcc.toFixed(2)}
              <br/>
              <strong>Total Rankings:</strong> {totalRankings}
            </div>
          </div>
        </div>
      </Metrics>
      </div>

      {/* Detailed Metrics Table */}
      <div className="metrics-table">
        <table>
          <thead>
            <tr>
              <th>Investigation</th>
              <th>Status</th>
              <th>Root Cause Acc.</th>
              <th>Runtime (s)</th>
              <th>Fault Local.</th>
              <th>Causal Chain</th>
              <th>Evidence Cov.</th>
              <th>Temporal Acc.</th>
              <th>Contrad. Hand.</th>
              <th>Unsup. Claims</th>
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
                  <td>{metrics.fault_localization_accuracy?.toFixed(2) ?? "N/A"}</td>
                  <td>{metrics.causal_chain_accuracy?.toFixed(2) ?? "N/A"}</td>
                  <td>{metrics.evidence_coverage?.toFixed(2) ?? "N/A"}</td>
                  <td>{metrics.temporal_ordering_accuracy?.toFixed(2) ?? "N/A"}</td>
                  <td>{metrics.contradiction_handling?.toFixed(2) ?? "N/A"}</td>
                  <td>{metrics.unsupported_claim_rate?.toFixed(2) ?? "N/A"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Baseline Comparison Section */}
      {Object.keys(baselineComparisons).length > 0 && (
        <div className="baseline-comparison">
          <h3>Baseline Comparison Across Investigations</h3>
          <div className="baseline-grid">
            <div className="baseline-card">
              <strong>Full Autopsy</strong>
              <p>{avgBaseline.full_autopsy.toFixed(2)}</p>
            </div>
            <div className="baseline-card">
              <strong>Dependency Only</strong>
              <p>{avgBaseline.dependency_only.toFixed(2)}</p>
            </div>
            <div className="baseline-card">
              <strong>Earliest Anomaly</strong>
              <p>{avgBaseline.earliest_anomaly.toFixed(2)}</p>
            </div>
            <div className="baseline-card">
              <strong>Threshold Only</strong>
              <p>{avgBaseline.threshold_only.toFixed(2)}</p>
            </div>
          </div>
        </div>
      )}

      {/* Per-Scenario Performance Section */}
      {Object.keys(scenarioPerformance).length > 0 && (
        <div className="scenario-performance">
          <h3>Per-Scenario Performance</h3>
          <table>
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Fault Local.</th>
                <th>Causal Acc.</th>
                <th>Evidence Cov.</th>
                <th>Temporal Acc.</th>
                <th>Contrad. Score</th>
                <th>Unsup. Rate</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(scenarioPerformance).flatMap(([invId, performances]) => performances.map((p) => (
                <tr key={`${invId}-${p.scenario_id}`}>
                  <td>
                    <strong>{p.scenario_name}</strong> ({p.scenario_id})
                  </td>
                  <td>{p.fault_localization.toFixed(2)}</td>
                  <td>{p.causal_accuracy.toFixed(2)}</td>
                  <td>{p.evidence_cov.toFixed(2)}</td>
                  <td>{p.temporal_accuracy.toFixed(2)}</td>
                  <td>{p.contradiction_score.toFixed(2)}</td>
                  <td>{p.unsupported_rate.toFixed(2)}</td>
                </tr>
              ))}
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Error Breakdown Section */}
      {Object.keys(errorBreakdowns).length > 0 && (
        <div className="error-breakdown">
          <h3>Error Breakdown</h3>
          <div className="breakdown-grid">
            {Object.entries(errorBreakdowns).map(([invId, breakdown]) => (
              <div key={invId} className="breakdown-item">
                <strong>Investigation {invId}</strong>
                <p>Mislocalized: {breakdown.mislocalized_faults}</p>
                <p>Chain Errors: {breakdown.chain_errors}</p>
                <p>Temporal Errors: {breakdown.temporal_errors}</p>
                <p>Unsupported Claims: {breakdown.unsupported_claims}</p>
                <p>Total Evidence: {breakdown.total_evidence}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Hypothesis Ranking Section */}
      {Object.keys(hypothesis comparisons).length > 0 && (
        <div className="hypothesis-ranking">
          <h3>Hypothesis Ranking Comparison</h3>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Hypothesis</th>
                <th>Score</th>
                <th>Causal Acc.</th>
                <th>Evidence</th>
                <th>Contrad.</th>
                <th>Assumptions</th>
              </tr>
            </thead>
            <tbody>
              {allRankings.map((r, i) => (
                <tr key={r.hypothesis_id}>
                  <td>{r.rank}</td>
                  <td>{r.title}</td>
                  <td>{r.score.toFixed(2)}</td>
                  <td>{r.causal_acc.toFixed(2)}</td>
                  <td>{r.evidence_count}</td>
                  <td>{r.contradiction_count}</td>
                  <td>{r.assumptions_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Aggregates Section */}
      {investigations.length > 0 && (
        <div className="aggregates">
          <h3>Aggregates</h3>
          <dl>
            <div>
              <dt>Average root cause accuracy</dt>
              <dd>{avgRootCauseAccuracy != null ? avgRootCauseAccuracy.toFixed(2) : "N/A"}</dd>
            </div>
            <div>
              <dt>Total investigations</dt>
              <dd>{investigations.length}</dd>
            </div>
            <div>
              <dt>Baseline: Full Autopsy</dt>
              <dd>{avgBaseline.full_autopsy.toFixed(2)}</dd>
            </div>
            <div>
              <dt>Baseline: Dependency Only</dt>
              <dd>{avgBaseline.dependency_only.toFixed(2)}</dd>
            </div>
          </dl>
        </div>
      )}
    </section>
  );
}