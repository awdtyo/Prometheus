/* =============================================================================
   Mission Overview Page
   -------------------------------------------------------
   Shows overall mission status, health check, and high-level summary.
   ============================================================================= */

import { useEffect, useState } from "react";
import { getHealth } from "../../api/client";
import type { HealthResponse } from "../../types/api";
import { EvaluationMetrics } from "../../types/domain";

export interface MissionOverviewMetrics {
  investigationsTotal: number;
  investigationsCompleted: number;
  activeInvestigations: number;
  totalHypotheses: number;
  rootCauseAccuracy: number;
}

export function MissionOverviewPage() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [metrics, setMetrics] = useState<MissionOverviewMetrics>({
    investigationsTotal: 0,
    investigationsCompleted: 0,
    activeInvestigations: 0,
    totalHypotheses: 0,
    rootCauseAccuracy: 0,
  });

  useEffect(() => {
    const controller = new AbortController();

    getHealth(controller.signal)
      .then((data) => {
        setHealth(data);
      })
      .catch(() => {
        setHealth(null);
      });

    return () => {
      controller.abort();
    };
  }, []);

  // Compute metrics from mock investigations (in a real app, these would
  // come from the API or a separate metrics service)
  const investigationCount = health ? 1 : 0; // placeholder

  return (
    <section className="page mission-overview">
      <div className="overview-header">
        <h2 className="header__title">Mission Overview</h2>
        <p className="header__subtitle">Spacecraft failure reconstruction status</p>
      </div>

      <div className="overview-grid">
        <div className="metric-card">
          <div className="metric-card__value">{investigationCount}</div>
          <div className="metric-card__label">Investigations</div>
        </div>
        <div className="metric-card">
          <div className="metric-card__value">3</div>
          <div className="metric-card__label">Scenarios</div>
        </div>
        <div className="metric-card">
          <div className="metric-card__value">2</div>
          <div className="metric-card__label">Hypotheses ranked</div>
        </div>
      </div>

      {health && (
        <div className="health-status">
          <span className="status-dot" />
          <span className="status-text">API reachable — {health.environment}</span>
        </div>
      )}

      <div className="overview-sections">
        <section className="section">
          <h3 className="section__title">Pipeline Status</h3>
          <ul className="pipeline-list">
            <li className="pipeline-item">
              <span className="pipeline-index">01</span>
              <div>
                <strong>Telemetry ingest</strong>
                <p>Normalize telemetry channels, event logs, and subsystem metadata into typed frames.</p>
              </div>
            </li>
            <li className="pipeline-item">
              <span className="pipeline-index">02</span>
              <div>
                <strong>Causal graph</strong>
                <p>Assemble subsystem dependencies and temporal relationships into an inspectable graph.</p>
              </div>
            </li>
            <li className="pipeline-item">
              <span className="pipeline-index">03</span>
              <div>
                <strong>Hypothesis ranking</strong>
                <p>Generate competing explanations, test them against evidence, and rank the survivors.</p>
              </div>
            </li>
          </ul>
        </section>

        <section className="section">
          <h3 className="section__title">Recent Investigations</h3>
          <ul className.recent-list>
            <li className="recent-item">
              <div className="recent-info">
                <strong>Power System Undervoltage</strong>
                <span className="recent-mission">scn_001</span>
              </div>
              <span className="recent-status status--completed">completed</span>
            </li>
            <li className="recent-item">
              <div className="recent-info">
                <strong>Thermal Overheat Analysis</strong>
                <span className="recent-mission">scn_002</span>
              </div>
              <span className="recent-status status--failed">failed</span>
            </li>
          </ul>
        </section>
      </div>
    </section>
  );
}