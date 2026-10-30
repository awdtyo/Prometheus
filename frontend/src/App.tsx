import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { API_DOCS_URL } from "./api/client";
import type { ConnectionStatus, HealthResponse } from "./types/api";
import { getHealth } from "./api/client";

type HealthState =
  | { status: "loading" }
  | { status: "online"; data: HealthResponse }
  | { status: "offline"; message: string };

const STATE_LABELS: Record<ConnectionStatus, string> = {
  loading: "Checking",
  online: "Operational",
  offline: "Unavailable",
};

const PIPELINE_MODULES = [
  {
    index: "01",
    title: "Telemetry ingest",
    description:
      "Normalize telemetry channels, event logs, and subsystem metadata into typed frames.",
  },
  {
    index: "02",
    title: "Causal graph",
    description:
      "Assemble subsystem dependencies and temporal relationships into an inspectable graph.",
  },
  {
    index: "03",
    title: "Hypothesis ranking",
    description:
      "Generate competing explanations, test them against evidence, and rank the survivors.",
  },
] as const;

function App() {
  const [health, setHealth] = useState<HealthState>({ status: "loading" });
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const controller = new AbortController();

    getHealth(controller.signal)
      .then((data) => {
        setHealth({ status: "online", data });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        setHealth({
          status: "offline",
          message: error instanceof Error ? error.message : "Unable to reach the API.",
        });
      });

    return () => {
      controller.abort();
    };
  }, []);

  const connectionStatus: ConnectionStatus = health.status;
  const stateLabel = STATE_LABELS[connectionStatus];
  const serviceName = health.status === "online" ? health.data.service : "—";
  const serviceVersion = health.status === "online" ? health.data.version : "—";
  const environment = health.status === "online" ? health.data.environment : "—";

  // Extract current path from router for sidebar/top bar active state
  const currentPath = location.pathname === "/" ? "/" : location.pathname;

  return (
    <div className="shell">
      <header className="topbar">
        <div className="topbar__left">
          <div className="brand">
            <div className="brand__mark" aria-hidden="true">
              <span />
            </div>
            <div>
              <p className="brand__name">Mission Autopsy</p>
              <p className="brand__sub">Incident reconstruction console</p>
            </div>
          </div>
        </div>

        <div className="topbar__center">
          <nav className="topbar-nav">
            <button
              className={`topbar-nav__item ${
                currentPath === "/" ? "topbar-nav__item--active" : ""
              }`}
              onClick={() => navigate("/")}
            >
              Mission Overview
            </button>
            <button
              className={`topbar-nav__item ${
                currentPath === "/scenarios" ? "topbar-nav__item--active" : ""
              }`}
              onClick={() => navigate("/scenarios")}
            >
              Scenario Explorer
            </button>
            <button
              className={`topbar-nav__item ${
                currentPath === "/workspace" ? "topbar-nav__item--active" : ""
              }`}
              onClick={() => navigate("/workspace")}
            >
              Investigation Workspace
            </button>
            <button
              className={`topbar-nav__item ${
                currentPath === "/causal-graph" ? "topbar-nav__item--active" : ""
              }`}
              onClick={() => navigate("/causal-graph")}
            >
              Causal Graph
            </button>
            <button
              className={`topbar-nav__item ${
                currentPath === "/hypotheses" ? "topbar-nav__item--active" : ""
              }`}
              onClick={() => navigate("/hypotheses")}
            >
              Hypothesis Analysis
            </button>
            <button
              className={`topbar-nav__item ${
                currentPath === "/evaluation" ? "topbar-nav__item--active" : ""
              }`}
              onClick={() => navigate("/evaluation")}
            >
              Evaluation Dashboard
            </button>
            <button
              className={`topbar-nav__item ${
                currentPath === "/investigation" ? "topbar-nav__item--active" : ""
              }`}
              onClick={() => navigate("/investigation")}
            >
              Live Investigation
            </button>
            <button
              className={`topbar-nav__item ${
                currentPath === "/causal-graph" ? "topbar-nav__item--active" : ""
              }`}
              onClick={() => navigate("/causal-graph")}
            >
              Causal Graph
            </button>
          </nav>
        </div>

        <div className="topbar__right">
          <HealthBadge status={connectionStatus} />
        </div>
      </header>

      <main>
        <section className="hero">
          <div className="hero__copy">
            <p className="eyebrow">Repository scaffold · status shell</p>
            <h1>Every failure leaves a trail.</h1>
            <p className="hero__lede">
              Mission Autopsy reconstructs the most plausible sequence of events behind a
              spacecraft failure by combining telemetry, event logs, subsystem dependencies,
              temporal relationships, and competing AI-generated hypotheses.
            </p>
            <div className="hero__actions">
              <a className="button" href={API_DOCS_URL} target="_blank" rel="noreferrer">
                Open API docs
              </a>
              <span className="endpoint">
                <span className="endpoint__method">GET</span>
                /api/health
              </span>
            </div>
          </div>

          <aside className="panel" aria-labelledby="status-title">
            <div className="panel__header">
              <h2 id="status-title">System status</h2>
              <span className="panel__meta">live check</span>
            </div>

            <dl className="status-grid">
              <div>
                <dt>State</dt>
                <dd>{stateLabel}</dd>
              </div>
              <div>
                <dt>Service</dt>
                <dd>{serviceName}</dd>
              </div>
              <div>
                <dt>Version</dt>
                <dd>{serviceVersion}</dd>
              </div>
              <div>
                <dt>Environment</dt>
                <dd>{environment}</dd>
              </div>
            </dl>

            {health.status === "loading" && (
              <p className="status-note" role="status">
                Contacting the backend…
              </p>
            )}
            {health.status === "offline" && (
              <p className="status-note status-note--error" role="status">
                {health.message} Start the stack with <code>./scripts/dev.sh</code>.
              </p>
            )}
            {health.status === "online" && (
              <p className="status-note status-note--ok" role="status">
                HTTP API reachable. The investigation pipeline is not wired yet.
              </p>
            )}
          </aside>
        </section>

        <section className="modules" aria-labelledby="modules-title">
          <div className="section-heading">
            <h2 id="modules-title">Planned pipeline</h2>
            <p>
              Scaffold only. No simulator, graph algorithm, agent, or investigation UI is
              implemented yet.
            </p>
          </div>

          <div className="module-grid">
            {PIPELINE_MODULES.map((module) => (
              <article className="module" key={module.index}>
                <span className="module__index">{module.index}</span>
                <h3>{module.title}</h3>
                <p>{module.description}</p>
                <span className="tag">Planned</span>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer className="footer">
        <span>Mission Autopsy · scaffold</span>
        <span>Business logic intentionally absent</span>
      </footer>
    </div>
  );
}

export default App;