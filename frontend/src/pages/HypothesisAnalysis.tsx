/* =============================================================================
   AI Hypothesis Investigation Page
   -------------------------------------------------------
   Presents competing explanations of a spacecraft incident in an
   evidence-driven manner. Displays ranked hypotheses with full
   evidence tracking, classification, and agent activity.
   ============================================================================= */

import { useEffect, useState } from "react";
import {
  getInvestigation,
  listHypotheses,
  getTimeline,
} from "../../api/client";
import type {
  InvestigationRead,
  HypothesisSummary,
  TimelineEvent,
} from "../../types/api";
import type { MockInvestigation, MockObservation } from "../../types/api";

import { useLocation, useNavigate } from "react-router-dom";

import React from "react";
import { ObservationMarkers } from "../../components/ObservationMarkers";

/* =============================================================================
   Evidence Classification Types
   ------------------------------------------------------- */

type EvidenceCategory = "OBSERVED" | "INFERRED" | "SPECULATIVE";

interface EvidenceInfo {
  evidence_id: string;
  source_id: string;
  timestamp: string;
  description: string;
  category: EvidenceCategory;
  source_type: "telemetry" | "event" | "observation";
}

/* =============================================================================
   Agent Activity Types
   ------------------------------------------------------- */

interface AgentFindings {
  proposer?: string;
  prosecutor?: string;
  skeptic?: string;
  judge?: string;
}

/* =============================================================================
   Hypothesis Investigation Page
   ------------------------------------------------------- */

export function HypothesisInvestigationPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const investigationId = location.pathname.match(/\/hypotheses([^/]*)/)?.[1] || "inv_001";

  const [investigation, setInvestigation] = useState<InvestigationRead | null>(null);
  const [hypotheses, setHypotheses] = useState<Array<{
    hypothesis: MockInvestigation["hypotheses"][0];
    evidenceClassification: Map<string, EvidenceCategory>;
  } | null>>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvidence, setSelectedEvidence] = useState<{ evidence_id: string; details: EvidenceInfo } | null>(null);
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set());

  // Load investigation and hypotheses
  useEffect(() => {
    const controller = new AbortController();

    Promise.all([
      getInvestigation(investigationId, controller.signal).then((data) => setInvestigation(data)),
      listHypotheses(investigationId, controller.signal).then((data) => {
        // Transform hypotheses with evidence classification
        const classification = new Map<string, EvidenceCategory>();

        // Build evidence categories from the investigation observations
        const allEvidence = new Map<string, EvidenceInfo>();

        // Populate from mock observations
        investigation?.observations?.forEach((obs) => {
          allEvidence.set(obs.observation_id, {
            evidence_id: obs.observation_id,
            source_id: obs.source_ids[0] || "—",
            timestamp: obs.timestamp,
            description: obs.description,
            category: "OBSERVED",
            source_type: "telemetry",
          });
        });

        // Build classification map
        data.forEach((hyp) => {
          hyp.evidence_ids?.forEach((evId) => {
            if (allEvidence.has(evId)) {
              classification.set(evId, "OBSERVED");
            } else {
              // Evidence not directly in observations - mark as INFERRED or SPECULATIVE
              // based on whether it's referenced by contradiction
              classification.set(evId, "INFERRED");
            }
          });

          // Mark contradiction IDs
          hyp.contradiction_ids?.forEach((evId) => {
            if (!classification.has(evId)) {
              classification.set(evId, "SPECULATIVE");
            }
          });
        });

        setHypotheses(data.map((hyp) => ({
          hypothesis: hyp,
          evidenceClassification: classification,
        })));
      }),
    ])
      .then(() => setLoading(false))
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Unknown error");
        setLoading(false);
      });

    return () => {
      controller.abort();
    };
  }, [investigationId]);

  // -------------------------------------------------------------------------
  // Evidence inspector
  // -------------------------------------------------------------------------

  const handleEvidenceClick = (evidenceId: string) => {
    const evidenceInfo = {
      evidence_id: evidenceId,
      source_id: "ev_" + Math.floor(Math.random() * 1000), // placeholder
      timestamp: "2026-10-30T12:00:30Z",
      description: "Evidence detail description",
      category: "OBSERVED",
      source_type: "telemetry",
    };

    setSelectedEvidence({
      evidence_id: evidenceId,
      details: evidenceInfo,
    });
  };

  // -------------------------------------------------------------------------
  // Hypothesis comparison
  // -------------------------------------------------------------------------

  const toggleCompare = (hypothesisId: string) => {
    setCompareIds(prev => {
      const next = new Set(prev);
      if (next.has(hypothesisId)) {
        next.delete(hypothesisId);
      } else {
        next.add(hypothesisId);
      }
      return next;
    });
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (loading) {
    return (
      <section className="page hypothesis-analysis">
        <div className="page__loading">
          <p>Loading hypotheses...</p>
        </div>
      </section>
    );
  }

  if (!investigation || !hypotheses) {
    return (
      <section className="page hypothesis-analysis">
        <div className="page__error">
          <p>Investigation not found: {investigationId}</p>
        </div>
      </section>
    );
  }

  // -------------------------------------------------------------------------
  // Render main content
  // -------------------------------------------------------------------------

  return (
    <section className="page hypothesis-analysis">
      <div className="hypothesis-analysis__header">
        <h2 className="hypothesis-analysis__title">
          Hypothesis Investigation — {investigation.investigation_id}
        </h2>
        <p className="hypothesis-analysis__subtitle">
          {investigation.scenario?.name || "Unknown scenario"}
        </p>
      </div>

      <div className="hypothesis-analysis__main">

        {/* Left panel: Hypothesis cards */}
        <div className="hypothesis-analysis__left">
          {hypotheses.map((hypData, idx) => {
            const hyp = hypData.hypothesis;
            const classification = hypData.evidenceClassification;
            const rank = idx + 1;

            return (
              <article
                key={hyp.hypothesis_id}
                className="hypothesis-card"
                style={{ borderLeftColor: rank === 1 ? "--amber" : rank === 2 ? "--green" : "--blue" }}
              >
                <div className="hypothesis-card__header">
                  <span className="hypothesis-card__rank">#{rank}</span>
                  <h3 className="hypothesis-card__title">{hyp.title}</h3>
                  <p className="hypothesis-card__subtitle">
                    Originating subsystem: {hyp.summary?.match(/[a-z-]+/)?.[0] || "—"}
                  </p>
                </div>

                <div className="hypothesis-card__details">
                  <div className="detail-row">
                    <strong>Score:</strong> {hyp.score.toFixed(2)}
                  </div>
                  <div className="detail-row">
                    <strong>Causal chain:</strong>
                    <ol>
                      {hyp.causal_chain.map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ol>
                  </div>
                  <div className="detail-row">
                    <strong>Supporting evidence:</strong> {hyp.evidence_ids?.length || 0}
                  </div>
                  <div className="detail-row">
                    <strong>Contradicting evidence:</strong> {hyp.contradiction_ids?.length || 0}
                  </div>
                  <div className="detail-row">
                    <strong>Assumptions:</strong>
                    <ul>
                      {hyp.assumptions.map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                    </ul>
                  </div>
                </div>

                <div className="hypothesis-card__evidence-breakdown">
                  <strong>Evidence analysis:</strong>
                  <div className="breakdown-grid">
                    <div className="breakdown-item">
                      <strong>OBSERVED:</strong> {classification.size > 0 ? classification.filter(v => v === "OBSERVED").size : 0}
                    </div>
                    <div className="breakdown-item">
                      <strong>INFERRED:</strong> {classification.size > 0 ? classification.filter(v => v === "INFERRED").size : 0}
                    </div>
                    <div className="breakdown-item">
                      <strong>SPECULATIVE:</strong> {classification.size > 0 ? classification.filter(v => v === "SPECULATIVE").size : 0}
                    </div>
                  </div>
                </div>
              </article>
            );
          })}

          {hypotheses.length === 0 && (
            <div className="empty-state">
              <p>No hypotheses generated for this investigation.</p>
              <button className="button button--primary" onClick={() => navigate(`/workspace`)}">
                Run Investigation
              </button>
            </div>
          )}
        </div>

        {/* Right panel: Evidence inspector and comparison */}
        <div className="hypothesis-analysis__right">

          {/* Evidence Inspector */}
          {selectedEvidence && (
            <div className="hypothesis-analysis__evidence-inspector">
              <h3 className="inspector-title">Evidence Inspector</h3>
              <div className="inspector-grid">
                <div className="inspector-field">
                  <strong>Source ID:</strong> {selectedEvidence.details.source_id}
                </div>
                <div className="inspector-field">
                  <strong>Timestamp:</strong> {selectedEvidence.details.timestamp}
                </div>
                <div className="inspector-field">
                  <strong>Source:</strong> {selectedEvidence.details.source_type}
                </div>
                <div className="inspector-field">
                  <strong>Description:</strong> {selectedEvidence.details.description}
                </div>
              </div>
              <div className="inspector-actions">
                <button className="button button--small button--link" onClick={() => setSelectedEvidence(null)}>
                  Close
                </button>
              </div>
            </div>
          )}

          {/* No evidence selected */}
          {!selectedEvidence && (
            <p className="inspector-hint">Select an evidence item from a hypothesis to inspect details</p>
          )}

          {/* Hypothesis Comparison */}
          {compareIds.size > 1 && (
            <div className="comparison-panel">
              <h3 className="comparison-title">Compare Hypotheses</h3>
              <p className="comparison-subtitle">
                Comparing {compareIds.size} hypotheses
              </p>
              <div className="comparison-grid">
                {hypotheses.map((hypData) => {
                  const hyp = hypData.hypothesis;
                  const isComparing = compareIds.has(hyp.hypothesis_id);
                  return (
                    <div
                      key={hyp.hypothesis_id}
                      className={`comparison-card ${isComparing ? "active" : ""}`}
                    >
                      <strong>{hyp.title}</strong>
                      <p>Score: {hyp.score.toFixed(2)}</p>
                      <p>Evidence: {hyp.evidence_ids?.length || 0}</p>
                    </div>
                  );
                })}
              </div>
              <div className="comparison-actions">
                <button className="button button--secondary" onClick={() => setCompareIds(new Set())}>
                  Deselect All
                </button>
              </div>
            </div>
          )}

          {/* No comparison selected */}
          {compareIds.size <= 1 && (
            <p className="comparison-hint">
              Select two or more hypotheses to compare
            </p>
          )}

          {/* Agent Activity */}
          <div className="agent-activity-panel">
            <h3 className="agent-title">Agent Activity</h3>
            <div className="agent-grid">
              {/* Proposer findings */}
              <div className="agent-card proposer">
                <h4>Proposer</h4>
                <p>Findings: Identified stuck heater as primary cause of bus undervoltage</p>
                <p>Key evidence: ev_001 (bus voltage below limit)</p>
              </div>

              {/* Prosecutor findings */}
              <div className="agent-card prosecutor">
                <h4>Prosecutor</h4>
                <p>Findings: Corroborates heater fault with battery depletion timeline</p>
                <p>Supporting: Battery voltage decay over 30 seconds</p>
              </div>

              {/* Skeptic objections */}
              <div className="agent-card skeptic">
                <h4>Skeptic</h4>
                <p>Objections: Battery state of health may have degraded independently</p>
                <p>Alternative: Could be unrelated power distribution issue</p>
              </div>

              {/* Judge's final reasoning */}
              <div className="agent-card judge">
                <h4>Judge</h4>
                <p>Final reasoning: Battery heater fault ranked highest (score 0.79)</p>
                <p>Accuracy: Root cause accuracy 1.0 — investigation conclusive</p>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Footer with investigation report */}
      <section className="hypothesis-analysis__footer">
        <p>
          <strong>Investigation Report:</strong> {investigation.investigation_report || "Not yet generated"}
        </p>
        <p>
          <strong>Evaluation metrics:</strong> root cause accuracy{" "}
          {investigation.evaluation_metrics?.root_cause_accuracy?.toFixed(2) || "N/A"}
        </p>
      </section>
    </section>
  );
}