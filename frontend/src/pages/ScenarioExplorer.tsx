/* =============================================================================
   Scenario Explorer Page
   -------------------------------------------------------
   View and manage scenario configurations. Lists available scenarios
   with their subsystem definitions and allows loading a scenario to
   start an investigation. Includes fault injection configuration.
   ============================================================================= */

import { useEffect, useState } from "react";
import { listScenarios } from "../../api/client";
import type { MockScenario } from "../../types/api";
import { ScenarioSummary } from "../../types/domain";
import { FaultInjectionPanel } from "../../components/FaultInjectionPanel";

/* =============================================================================
   Scenario Explorer Page
   ------------------------------------------------------- */

export function ScenarioExplorerPage() {
  const [scenarios, setScenarios] = useState<MockScenario[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    listScenarios(controller.signal)
      .then((data) => {
        setScenarios(data);
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Unknown error");
        setLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, []);

  if (loading) {
    return (
      <section className="page scenario-explorer">
        <div className="page__loading">
          <p>Loading scenarios...</p>
        </div>
      </section>
    );
  }

  return (
    <section className="page scenario-explorer">
      <div className="page__header">
        <h2 className="page__title">Scenario Explorer</h2>
        <p className="page__subtitle">Available mission scenarios</p>
      </div>

      {error && (
        <div className="error-banner">
          <p>{error}</p>
        </div>
      )}

      <div className="scenarios-grid">
        {scenarios.map((scenario) => (
          <article key={scenario.scenario_id} className="scenario-card">
            <div className="scenario-card__header">
              <h3 className="scenario-card__name">{scenario.name}</h3>
              <p className="scenario-card__description">
                {scenario.description}
              </p>
            </div>
            <div className="scenario-card__meta">
              <span className="meta-item">
                <strong>Mission start:</strong> {scenario.mission_start_utc}
              </span>
              <span className="meta-item">
                <strong>Mission duration:</strong> {calculateMissionDuration(scenario.mission_start_utc)}
              </span>
              <span className="meta-item">
                <strong>Participating subsystems:</strong> {scenario.subsystems.join(", ")}
              </span>
            </div>
            <div className="scenario-card__actions">
              <button className="button button--secondary">
                Load Scenario
              </button>
              <FaultInjectionPanel
                onSubmit={({ fault_type, target_subsystem, target_parameter, start_time, duration_seconds, magnitude, parameters }) => {
                  // Handle fault injection submission
                  console.log("Fault configuration submitted:", {
                    fault_type,
                    target_subsystem,
                    target_parameter,
                    start_time,
                    duration_seconds,
                    magnitude,
                    parameters,
                  });
                  // In a real implementation, this would call POST /api/v1/runs
                  // with the fault configuration
                }}
              />
            </button>
            <button className="button button--tertiary">
              Delete
              <span className="ml-2">✕</span>
            </button>
          </article>
        ))}
      </div>

      {!scenarios.length && (
        <div className="empty-state">
          <p>No scenarios available. Add scenario YAML configs to proceed.</p>
        </div>
      )}
    </section>
  );
}

/* -------------------------------------------------------
   Helper: calculate mission duration from start time
   ------------------------------------------------------- */

function calculateMissionDuration(startUtc: string): string {
  // In a real implementation, this would calculate the duration
  // from mission_start_utc to present or mission end time
  // For now, return a descriptive string
  return "Variable (mission-dependent)";
}