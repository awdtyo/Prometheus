/* =============================================================================
   Investigation Workspace Page
   -------------------------------------------------------
   Active investigation dashboard showing the current investigation state,
   run timestamps, observations, graph, hypotheses, and now:
   - Telemetry chart with multiple subsystem parameters
   - Mission event timeline
   - Observation markers with cross-linking
   ============================================================================= */

import { useEffect, useState } from "react";
import {
  listInvestigations,
  getInvestigation,
  getTimeline,
} from "../../api/client";
import type {
  InvestigationSummary,
  InvestigationRead,
  TimelineEvent,
} from "../../types/api";
import type { MockInvestigation, MockObservation } from "../../types/api";

import { useLocation, useNavigate } from "react-router-dom";

import React from "react";
import { TelemetryChart, TelemetryEmptyState, TelemetryErrorState } from "../../components/TelemetryChart";
import { EventTimeline, EventTimelineEmpty } from "../../components/EventTimeline";
import { ObservationMarkers } from "../../components/ObservationMarkers";

/* -------------------------------------------------------
   Types for telemetry chart props
   ------------------------------------------------------- */

interface TelemetryChartData {
  timestamp: string; // ISO 8601 UTC
  subsystem: SubsystemId;
  parameter: ParameterName;
  value: number;
  unit: string;
}

/* -------------------------------------------------------

   Investigation Workspace Page
   ------------------------------------------------------- */

export function InvestigationWorkspacePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const investigationId = location.pathname.match(/\/workspace([^/]*)/)?.[1] || "";

  const [investigation, setInvestigation] = useState<InvestigationRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedRange, setSelectedRange] = useState<[string, string] | null>(null);

  // Timeline events from API (populated by getTimeline)
  const [timelineEvents, setTimelineEvents] = useState<TimelineEvent[]>([]);

  // Load investigation data
  useEffect(() => {
    const controller = new AbortController();

    // Parallel: get investigation and its timeline
    Promise.all([
      getInvestigation(investigationId || "inv_001", controller.signal).then((data) => setInvestigation(data)),
      getTimeline(investigationId || "inv_001", controller.signal).then((data) => {
        // Transform API timeline events to internal format
        // and store for EventTimeline component
        setTimelineEvents(data);
      }),
    ])
      .then(() => {
        // After data loads, set up telemetry chart data
        if (investigation) {
          setupTelemetryChartData(investigation);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Unknown error");
        setLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [investigationId]);

  // -------------------------------------------------------------------------
  // Setup telemetry chart data from investigation observations and graph
  // -------------------------------------------------------------------------

  const [telemetryData, setTelemetryData] = useState<TelemetryChartData[]>([]);
  const [subsystems, setSubsystems] = useState<SubsystemId[]>([]);
  const [missionStartUtc, setMissionStartUtc] = useState<string>("");

  const setupTelemetryChartData = (inv: InvestigationRead) => {
    // Build telemetry data from observations and graph
    const data: TelemetryChartData[] = [];

    // Add observations as telemetry points
    inv.observations.forEach((obs) => {
      data.push({
        timestamp: obs.timestamp,
        subsystem: obs.subsystem,
        parameter: obs.observation_type,
        value: obs.observed_value,
        unit: "V", // Default unit; in production, use actual unit from config
      });
    });

    // Add graph node timestamps as reference points
    inv.graph.nodes.forEach((node) => {
      if (node.timestamp) {
        // Find observations matching this subsystem
        const matchingObs = inv.observations?.filter(
          (o) => o.subsystem === (node.label?.match(/^[a-z-]+/)?.[0] || "power")
        );
        if (matchingObs?.length > 0) {
          matchingObs.forEach((obs) => {
            data.push({
              timestamp: obs.timestamp,
              subsystem: obs.subsystem,
              parameter: obs.observation_type,
              value: obs.observed_value,
              unit: "V",
            });
          });
        }
      }
    });

    setTelemetryData(data);

    // Derive unique subsystems from data and scenario
    const derivedSubsystems = [...new Set(data.map((d) => d.subsystem))];
    setSubsystems(derivedSubsystems.length > 0 ? derivedSubsystems : ["power"]);
    setMissionStartUtc(inv.scenario?.mission_start_utc || "2026-10-30T12:00:00Z");
  };

  // -------------------------------------------------------------------------
  // State for cross-linking
  // -------------------------------------------------------------------------

  const [highlightedObservation, setHighlightedObservation] = useState<MockObservation | null>(null);
  const [showObservationDetail, setShowObservationDetail] = useState(false);

  // -------------------------------------------------------------------------
  // Compute chart domain
  // -------------------------------------------------------------------------

  const allValues = telemetryData.map((d) => d.value);
  const minValue = allValues.length > 0 ? Math.min(...allValues) * 0.9 : 20;
  const maxValue = allValues.length > 0 ? Math.max(...allValues) * 1.1 : 30;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (loading) {
    return (
      <section className="page investigation-workspace">
        <div className="page__loading">
          <p>Loading investigation...</p>
        </div>
      </section>
    );
  }

  if (!investigation) {
    return (
      <section className="page investigation-workspace">
        <div className="page__error">
          <p>Investigation not found.</p>
        </div>
      </section>
    );
  }

  // -------------------------------------------------------------------------
  // Render main content
  // -------------------------------------------------------------------------

  return (
    <section className="page investigation-workspace">
      <div className="workspace-header">
        <h2 className="workspace-header__title">
          Investigation {investigation.investigation_id}
        </h2>
        <div className="workspace-header__status">
          <span className="status-dot status-dot--{investigation.status}" />
          <span className="status-text">{investigation.status}</span>
        </div>
      </div>

      <div className="workspace-grid">

        {/* LEFT COLUMN: Main panels (reduced width for new components) */}
        <section className="workspace-panel" style={{ width: "52%" }}>

          {/* Run Timestamps */}
          <div className="workspace-subpanel">
            <h3 className="panel__title">Run Timestamps</h3>
            <dl className="timeline-dl">
              <div>
                <dt>Created at</dt>
                <dd>{investigation.run_timestamps.created_at}</dd>
              </div>
              {investigation.run_timestamps.started_at && (
                <div>
                  <dt>Started at</dt>
                  <dd>{investigation.run_timestamps.started_at}</dd>
                </div>
              )}
              {investigation.run_timestamps.completed_at && (
                <div>
                  <dt>Completed at</dt>
                  <dd>{investigation.run_timestamps.completed_at}</dd>
                </div>
              )}
            </dl>
          </div>

          {/* Observations */}
          <div className="workspace-subpanel">
            <h3 className="panel__title">Observations</h3>
            <ul className="observations-list">
              {investigation.observations.map((obs) => (
                <li key={obs.observation_id} className="observation-item">
                  <div className="observation-info">
                    <strong>{obs.observation_type}</strong> in {obs.subsystem}
                    <span className="observation-severity status-dot status-dot--{obs.severity}"></span>
                  </div>
                  <div className="observation-desc">
                    {obs.description}
                  </div>
                  <div className="observation-meta">
                    <span>
                      Value: {obs.observed_value}{obs.threshold ? ` (threshold: ${obs.threshold} V)` : ""}</span>
                    <span>Sources: {obs.source_ids.length}</span>
                  </div>
                </li>
              ))}
            </ul>
            {investigation.observations.length === 0 && (
              <p className="empty-observations">No observations yet.</p>
            )}
          </div>

          {/* Graph */}
          <div className="workspace-subpanel">
            <h3 className="panel__title">Graph</h3>
            <div className="graph-summary">
              <p>Nodes: {investigation.graph.nodes.length}</p>
              <p>Edges: {investigation.graph.edges.length}</p>
              <details className="graph-details">
                <summary>Show node details</summary>
                <ul>
                  {investigation.graph.nodes.map((node) => (
                    <li key={node.node_id}>
                      {node.label} ({node.node_type}){node.timestamp && ` @ ${node.timestamp}`}
                    </li>
                  ))}
                </ul>
              </details>
              <details className="graph-details">
                <summary>Show edge details</summary>
                <ul>
                  {investigation.graph.edges.map((edge) => (
                    <li key={edge.edge_id}>
                      {edge.source} → {edge.target}
                      <span className="edge-confidence">confidence: {edge.confidence}</span>
                    </li>
                  ))}
                </ul>
              </details>
            </div>
          </div>
        </section>

        {/* RIGHT COLUMN: New telemetry & timeline components */}
        <section className="workspace-panel" style={{ width: "48%" }}>

          {/* Telemetry Chart */}
          <div className="workspace-subpanel">
            <h3 className="panel__title">Telemetry</h3>
            <p className="subpanel-hint">
              Multiple subsystem parameters with nominal ranges and thresholds
            </p>
            {telemetryData.length > 0 ? (
              <TelemetryChart
                data={telemetryData}
                subsystems={subsystems}
                missionStartUtc={missionStartUtc}
                observations={investigation.observations}
                selectedRange={selectedRange ? [new Date(selectedRange[0]), new Date(selectedRange[1])] : undefined}
                onRangeChange={(range: [string, string]) => {
                  setSelectedRange(range);
                }}
                onObservationClick={(obs) => {
                  setHighlightedObservation(obs);
                  setShowObservationDetail(true);
                }}
              />
            ) : (
              <TelemetryEmptyState />
            )}
            {error && <TelemetryErrorState error={error} />}
          </div>

          {/* Event Timeline */}
          <div className="workspace-subpanel">
            <h3 className="panel__title">Mission Events</h3>
            <p className="subpanel-hint">
              Chronological event log with severity distinction
            </p>
            {timelineEvents.length > 0 ? (
              <EventTimeline
                events={timelineEvents}
                observations={investigation.observations}
                selectedRange={selectedRange ? [new Date(selectedRange[0]), new Date(selectedRange[1])] : undefined}
                onEventClick={(event, observation) => {
                  // Handle event click - highlight observation if available
                  if (observation) {
                    setHighlightedObservation(observation);
                    setShowObservationDetail(true);
                  }
                }}
                missionStartUtc={missionStartUtc}
              />
            ) : (
              <EventTimelineEmpty />
            )}
          </div>

          {/* Observation Detail */}
          <div className="workspace-subpanel">
            <h3 className="panel__title">Observations Detail</h3>
            {highlightedObservation ? (
              <div>
                <p><strong>ID:</strong> {highlightedObservation.observation_id}</p>
                <p><strong>Timestamp:</strong> {highlightedObservation.timestamp}</p>
                <p><strong>Subsystem:</strong> {highlightedObservation.subsystem}</p>
                <p><strong>Type:</strong> {highlightedObservation.observation_type}</p>
                <p><strong>Description:</strong> {highlightedObservation.description}</p>
                <p><strong>Observed Value:</strong> {highlightedObservation.observed_value}{highlightedObservation.threshold ? ` (threshold: ${highlightedObservation.threshold} V)` : ""}</p>
                <p><strong>Severity:</strong> {highlightedObservation.severity}</p>
                <p><strong>Sources:</strong> {highlightedObservation.source_ids?.join(", ") || "—"}</p>
                <button className="button button--small button--link" onClick={() => setShowObservationDetail(false)}>
                  Close
                </button>
              </div>
            ) : (
              <p>Select an observation marker or event to view details.</p>
            )}
          </div>
        </section>

      </div>

      <section className="workspace-footer">
        <p>
          <strong>Report:</strong> {investigation.investigation_report || "Not yet generated"}
        </p>
        <p>
          <strong>Evaluation metrics:</strong> root cause accuracy{" "}
          {investigation.evaluation_metrics?.root_cause_accuracy?.toFixed(2) || "N/A"}
        </p>
      </section>
    </section>
  );
}