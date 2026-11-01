import { useEffect, useMemo, useState, useRef } from "react";
import { useParams, Link } from "react-router-dom";

import {
  useInvestigation,
  useTimeline,
  subscribeToInvestigationProgress,
  problemFromError,
} from "../api/client";
import { Empty } from "../components/Empty";
import { FaultInjectionForm } from "../components/FaultInjectionForm";

import type { TimelineEvent } from "../types/api";

export function InvestigationWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const { data: investigation, error } = useInvestigation(id ?? null);
  const { data: timeline } = useTimeline(id ?? null);

  // Check for replayed demo data stored in localStorage
  const demoData = useMemo(() => {
    if (!id) return null;
    try {
      const raw = localStorage.getItem("demo-investigation");
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed.run_result;
    } catch {
      return null;
    }
  }, [id]);

  const effectiveInvestigation = demoData ?? investigation;
  const events: TimelineEvent[] = timeline?.events ?? [];
  const [progressEvents, setProgressEvents] = useState<{
    investigation_id: string;
    status: string;
    stage: string;
    progress: number;
    message: string;
    timestamp: string;
  }[]>([]);

  const eventSourceRef = useRef<{ abort: () => void } | null>(null);

  useEffect(() => {
    if (!id) return;
    const sub = subscribeToInvestigationProgress(id, (ev) => {
      setProgressEvents((prev) => [...prev, ev]);
    });
    eventSourceRef.current = sub;
    return () => sub.abort();
  }, [id]);

  // Replay progress events from demo data with short delays
  useEffect(() => {
    if (!demoData || !id) return;
    const demoProgress = localStorage.getItem("demo-investigation-progress");
    if (!demoProgress) return;
    try {
      const events = JSON.parse(demoProgress);
      let i = 0;
      const timer = setInterval(() => {
        if (i >= events.length) {
          clearInterval(timer);
          return;
        }
        setProgressEvents((prev) => [...prev, events[i]]);
        i++;
      }, 400);
      return () => clearInterval(timer);
    } catch {
      // ignore
    }
  }, [demoData, id]);
  if (error && !effectiveInvestigation) {
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

  const latestProgress = progressEvents[progressEvents.length - 1];

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
          {latestProgress && (
            <span style={pageStyles.progressText}>
              {" | " + latestProgress.stage + " (" + latestProgress.progress + "%)"}
            </span>
          )}
          <span style={pageStyles.modeBadge}>
            {investigation.metadata?.mode ? `mode: ${investigation.metadata.mode}` : null}
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

        {progressEvents.length > 0 && (
          <div style={pageStyles.section}>
            <h3 style={pageStyles.sectionTitle}>Progress events</h3>
            <div style={pageStyles.timeline}>
              {progressEvents.map((ev) => (
                <div key={ev.timestamp} style={pageStyles.eventRow}>
                  <div style={pageStyles.eventTime}>{ev.timestamp}</div>
                  <div style={pageStyles.eventBody}>
                    <strong>{ev.stage}</strong> — {ev.message}
                    <br />
                    <span style={pageStyles.severity}>[{ev.status} · {ev.progress}%]</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <div style={pageStyles.actions}>
        <Link to={`/hypotheses?inv=${effectiveInvestigation.id}`}>View hypotheses</Link>
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
  modeBadge: {
    marginLeft: 10,
    fontSize: 0.75,
    fontFamily: "var(--mono)",
    color: "var(--accent-foreground)",
    background: "rgba(240, 165, 43, 0.1)",
    padding: "2px 8px",
    borderRadius: 4,
    border: "1px solid var(--accent)",
  },
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
