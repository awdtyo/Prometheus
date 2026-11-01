import { useParams, Link } from "react-router-dom";

import {
  useInvestigation,
  useTimeline,
  problemFromError,
} from "../api/client";
import { Loading } from "../components/Loading";
import { Empty } from "../components/Empty";
import { FaultInjectionForm } from "../components/FaultInjectionForm";

import type { TimelineEvent } from "../types/api";

export function InvestigationWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const { data: investigation, error, isLoading } = useInvestigation(id ?? null);
  const { data: timeline } = useTimeline(id ?? null);

  const events: TimelineEvent[] = timeline?.events ?? [];

  if (isLoading) return <Loading />;
  if (error) {
    const p = problemFromError(error);
    return (
      <div style={pageStyles.container}>
        <h1>Investigation</h1>
        <p>Unable to load investigation.</p>
        <p>{p.detail}</p>
      </div>
    );
  }
  if (!investigation) {
    return (
      <div style={pageStyles.container}>
        <h1>Investigation</h1>
        <p>No investigation selected.</p>
      </div>
    );
  }

  const statusColor: Record<string, string> = {
    pending: "var(--amber)",
    running: "var(--amber)",
    completed: "var(--green)",
    failed: "var(--red)",
    cancelled: "var(--faint)",
  };

  return (
    <div style={pageStyles.container}>
      <nav style={pageStyles.breadcrumbs}>
        <Link to="/">Scenarios</Link>{" "}{">"}{" "}<span>Investigation</span>
      </nav>

      <h1>Investigation Workspace</h1>

      <div style={pageStyles.headerCard}>
        <div>
          <h2 style={pageStyles.title}>{investigation.title}</h2>
          <p style={pageStyles.sub}>
            Scenario: {investigation.scenario_id}{" "}\u2022{" "} Created:{" "}
            {investigation.created_at}
          </p>
        </div>
        <div style={pageStyles.statusBadge}>
          <span
            style={{ ...pageStyles.statusDot, background: statusColor[investigation.status] }}
          />
          <span style={pageStyles.statusText}>{investigation.status}</span>
          <span style={pageStyles.progressText}>
            {investigation.progress}% complete
          </span>
        </div>
      </div>

      <FaultInjectionForm scenarioId={investigation.scenario_id} />

      <div style={pageStyles.section}>
        <h3 style={pageStyles.sectionTitle}>Timeline</h3>
        {events.length === 0 ? (
          <Empty message="No timeline events yet." />
        ) : (
          <div style={pageStyles.timeline}>
            {events.map((event) => (
              <div key={event.event_id} style={pageStyles.eventRow}>
                <div style={pageStyles.eventTime}>{event.timestamp}</div>
                <div style={pageStyles.eventBody}>
                  <strong>{event.subsystem}</strong> — {event.event_type}
                  <br />
                  {event.description}
                  <span style={pageStyles.severity}>[{event.severity}]</span>
                </div>
                {event.metadata && Object.keys(event.metadata).length > 0 && (
                  <div style={pageStyles.meta}>
                    {JSON.stringify(event.metadata)}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={pageStyles.actions}>
        <Link to={`/hypotheses?inv=${investigation.id}`}>View hypotheses</Link>
        &nbsp;|&nbsp;
        <Link to="/causal-graph">Causal graph</Link>
        &nbsp;|&nbsp;
        <Link to="/evaluation">Evaluation</Link>
      </div>
    </div>
  );
}

const pageStyles: Record<string, React.CSSProperties> = {
  container: { padding: 24, color: "var(--text)", fontFamily: "system-ui, sans-serif" },
  breadcrumbs: { marginBottom: 10, fontFamily: "var(--mono)", fontSize: 0.8, color: "var(--faint)" },
  headerCard: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 16,
    padding: 16,
    border: "1px solid var(--border)",
    borderRadius: 8,
    background: "var(--surface)",
    marginBottom: 20,
  },
  title: { margin: "0 0 6px", fontSize: 1.3 },
  sub: { margin: 0, color: "var(--muted)", fontSize: 0.85 },
  statusBadge: { display: "flex", alignItems: "center", gap: 8 },
  statusDot: { width: 8, height: 8, borderRadius: "50%" },
  statusText: { fontFamily: "var(--mono)", fontSize: 0.85, fontWeight: 600 },
  progressText: { marginLeft: 10, fontFamily: "var(--mono)", fontSize: 0.8, color: "var(--muted)" },
  section: { marginTop: 20 },
  sectionTitle: { margin: "0 0 10px", fontSize: 1, color: "var(--muted)", fontFamily: "var(--mono)" },
  timeline: { display: "flex", flexDirection: "column", gap: 8 },
  eventRow: {
    display: "flex",
    gap: 10,
    padding: 10,
    border: "1px solid var(--border)",
    borderRadius: 6,
    background: "rgba(14, 20, 30, 0.4)",
  },
  eventTime: {
    minWidth: 150,
    fontFamily: "var(--mono)",
    fontSize: 0.8,
    color: "var(--faint)",
  },
  eventBody: { flex: 1, fontSize: 0.9 },
  severity: {
    marginLeft: 8,
    fontFamily: "var(--mono)",
    fontSize: 0.75,
    padding: "1px 6px",
    border: "1px solid var(--border)",
    borderRadius: 4,
    color: "var(--faint)",
  },
  meta: { marginTop: 6, fontFamily: "var(--mono)", fontSize: 0.75, color: "var(--faint)" },
  actions: { marginTop: 20, fontFamily: "var(--mono)", fontSize: 0.85, color: "var(--muted)" },
};
