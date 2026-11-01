import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";

import { useScenarios, useCreateInvestigation, getDemo, problemFromError } from "../api/client";
import { Loading } from "../components/Loading";
import { Empty } from "../components/Empty";
import type { ScenarioSummary } from "../types/api";

export function ScenariosPage() {
  const { data, error, isLoading } = useScenarios();
  const navigate = useNavigate();
  const { create, isLoading: creating, error: createError } = useCreateInvestigation();
  const [started, setStarted] = useState<string | null>(null);
  const [replaying, setReplaying] = useState(false);

  const scenarios: ScenarioSummary[] = data?.items ?? [];

  if (isLoading) return <Loading />;
  if (error) {
    const p = problemFromError(error);
    return (
      <div style={pageStyles.container}>
        <h1>Scenarios</h1>
        <p>Unable to load scenarios.</p>
        <p>{p.detail}</p>
      </div>
    );
  }

  const handleStart = (scenario: ScenarioSummary) => {
    create({
      scenario_id: scenario.id,
      title: `Investigation of ${scenario.name}`,
    }).then((inv) => {
      setStarted(inv.id);
      navigate(`/investigation/${inv.id}`);
    });
  };

  const handleReplay = async () => {
    setReplaying(true);
    try {
      const demo = await getDemo("battery_failure");
      localStorage.setItem(
        "demo-investigation",
        JSON.stringify({
          run_result: demo.run_result,
          progress_events: demo.progress_events,
        }),
      );
      navigate("/investigation/demo-battery-failure");
    } catch (err) {
      setReplaying(false);
      console.error("Replay failed:", err);
    }
  };

  return (
    <div style={pageStyles.container}>
      <h1>Scenarios</h1>
      <p>Select a scenario to start an investigation.</p>

      {createError && (
        <div style={pageStyles.errorBanner}>
          Could not start investigation: {(createError as Error).message}
        </div>
      )}

      {started && (
        <p style={pageStyles.ok}>
          Investigation started. <Link to={`/investigation/${started}`}>Open investigation</Link>
        </p>
      )}

      <div style={pageStyles.list}>
        {scenarios.length === 0 ? (
          <Empty message="No scenarios available." />
        ) : (
          scenarios.map((scenario) => (
            <article key={scenario.id} style={pageStyles.card}>
              <div style={pageStyles.cardBody}>
                <h2 style={pageStyles.cardTitle}>{scenario.name}</h2>
                <p style={pageStyles.cardDesc}>{scenario.description}</p>
                <div style={pageStyles.meta}>
                  <span>Subsystems: {scenario.subsystem_ids.join(", ")}</span>
                  <span>Duration: {scenario.duration_seconds}s</span>
                </div>
              </div>
              <button
                style={pageStyles.startButton}
                disabled={creating}
                onClick={() => handleStart(scenario)}
              >
                {creating ? "Starting…" : "Start investigation"}
              </button>
            </article>
          ))
        )}
      </div>

      <div style={pageStyles.section}>
        <h3 style={pageStyles.sectionTitle}>Replay recorded demo</h3>
        <p style={pageStyles.cardDesc}>
          Replay a previously recorded real LLM run of the battery_failure scenario,
          complete with progress events and full results.
        </p>
        <button
          style={pageStyles.startButton}
          disabled={replaying}
          onClick={handleReplay}
        >
          {replaying ? "Replaying…" : "Replay recorded real run"}
        </button>
      </div>
    </div>
  );
}

const pageStyles: Record<string, React.CSSProperties> = {
  container: { padding: 24, color: "var(--text)", fontFamily: "system-ui, sans-serif" },
  errorBanner: {
    marginBottom: 16,
    padding: 10,
    background: "rgba(255, 107, 107, 0.15)",
    border: "1px solid var(--red)",
    color: "var(--red)",
    fontSize: 0.85,
    fontFamily: "var(--mono)",
  },
  ok: {
    margin: "12px 0",
    color: "var(--green)",
    fontFamily: "var(--mono)",
    fontSize: 0.85,
  },
  list: { display: "grid", gap: 12, marginTop: 20 },
  card: {
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 16,
    background: "var(--surface)",
  },
  cardBody: { marginBottom: 12 },
  cardTitle: { margin: "0 0 6px", fontSize: 1.1 },
  cardDesc: { margin: "0 0 10px", color: "var(--muted)", fontSize: 0.9 },
  meta: {
    display: "flex",
    gap: 16,
    fontFamily: "var(--mono)",
    fontSize: 0.78,
    color: "var(--faint)",
  },
  startButton: {
    padding: "8px 14px",
    background: "var(--amber)",
    color: "#161006",
    border: "none",
    borderRadius: 6,
    fontWeight: 650,
    cursor: "pointer",
    width: "100%",
  },
  section: {
    marginTop: 32,
    padding: 16,
    border: "1px solid var(--border)",
    borderRadius: 8,
    background: "var(--surface-raised)",
  },
  sectionTitle: { margin: "0 0 10px", fontSize: 1.1, color: "var(--muted)", fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: "0.05em" },
};
