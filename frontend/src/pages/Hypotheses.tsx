import { useSearchParams } from "react-router-dom";

import { useHypotheses } from "../api/client";
import { Loading } from "../components/Loading";
import { Empty } from "../components/Empty";
import type { Hypothesis } from "../types/api";

export function HypothesesPage() {
  const [searchParams] = useSearchParams();
  const investigationId = searchParams.get("inv") || null;
  const { data, error, isLoading } = useHypotheses(investigationId);

  const hypotheses: Hypothesis[] = data?.hypotheses ?? [];
  const ordered = [...hypotheses].sort((a, b) => b.score - a.score);
  const accepted = ordered.filter((h) => h.score >= 0.4);
  const rejected = ordered.filter((h) => h.score < 0.4);

  if (isLoading) return <Loading />;
  if (error) {
    return (
      <div style={pageStyles.container}>
        <h1>Hypotheses</h1>
        <p>Unable to load hypotheses.</p>
      </div>
    );
  }

  return (
    <div style={pageStyles.container}>
      <h1>Hypothesis Analysis</h1>
      <p>Ranked competing explanations, highest score first.</p>

      {ordered.length === 0 ? (
        <Empty message="No hypotheses for this investigation." />
      ) : (
        <>
          {accepted.length > 0 && (
            <div style={pageStyles.sectionGroup}>
              <h2 style={pageStyles.sectionTitle}>Leading hypotheses</h2>
              <div style={pageStyles.cards}>
                {accepted.map((hyp) => (
                  <article
                    key={hyp.hypothesis_id}
                    style={pageStyles.hypothesisCard}
                  >
                    <div style={pageStyles.cardHead}>
                      <h2 style={pageStyles.cardTitle}>{hyp.title}</h2>
                      <span style={pageStyles.rankBadge}>#{ordered.indexOf(hyp) + 1}</span>
                    </div>
                    <p style={pageStyles.cardSummary}>{hyp.summary}</p>

                    <div style={pageStyles.scoreRow}>
                      <div style={pageStyles.metric}>
                        <span style={pageStyles.metricLabel}>Score</span>
                        <div style={pageStyles.scoreBar}>
                          <div
                            style={{
                              ...pageStyles.scoreBarFill,
                              width: `${hyp.score * 100}%`,
                            }}
                          />
                        </div>
                        <span style={pageStyles.metricValue}>{hyp.score.toFixed(2)}</span>
                      </div>
                      <div style={pageStyles.metric}>
                        <span style={pageStyles.metricLabel}>Confidence</span>
                        <span style={pageStyles.metricValue}>{hyp.confidence.toFixed(2)}</span>
                      </div>
                      <div style={pageStyles.metric}>
                        <span style={pageStyles.metricLabel}>Evidence</span>
                        <span style={pageStyles.metricValue}>{hyp.evidence_ids.length}</span>
                      </div>
                      <div style={pageStyles.metric}>
                        <span style={pageStyles.metricLabel}>Contradicts</span>
                        <span style={pageStyles.metricValue}>{hyp.contradiction_ids.length}</span>
                      </div>
                    </div>

                    {hyp.causal_chain.length > 0 && (
                      <div style={pageStyles.chain}>
                        <span style={pageStyles.chainLabel}>Causal chain</span>
                        <div style={pageStyles.steps}>
                          {hyp.causal_chain.map((step, i) => (
                            <div key={i} style={pageStyles.step}>
                              {i + 1}. {step}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div style={pageStyles.tags}>
                      {hyp.assumptions.length > 0 && (
                        <span style={pageStyles.tag}>
                          Assumptions: {hyp.assumptions.join(", ")}
                        </span>
                      )}
                      {hyp.metadata?.preliminary_evidence_ids?.length > 0 && (
                        <span style={pageStyles.tagPreliminary}>
                          Preliminary evidence: {hyp.metadata?.preliminary_evidence_ids?.join(", ")}
                        </span>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </div>
          )}

          {rejected.length > 0 && (
            <div style={pageStyles.sectionGroup}>
              <h2 style={pageStyles.sectionTitle}>Rejected hypotheses</h2>
              <div style={pageStyles.cards}>
                {rejected.map((hyp) => (
                  <article
                    key={hyp.hypothesis_id}
                    style={{
                      ...pageStyles.hypothesisCard,
                      opacity: 0.5,
                      borderColor: "var(--border)",
                    }}
                  >
                    <div style={pageStyles.cardHead}>
                      <h2 style={pageStyles.cardTitle}>{hyp.title}</h2>
                      <span style={pageStyles.rankBadge}>#{ordered.indexOf(hyp) + 1}</span>
                      <span style={pageStyles.tagRejected}>Rejected</span>
                    </div>
                    <p style={pageStyles.cardSummary}>{hyp.summary}</p>

                    <div style={pageStyles.scoreRow}>
                      <div style={pageStyles.metric}>
                        <span style={pageStyles.metricLabel}>Score</span>
                        <div style={pageStyles.scoreBar}>
                          <div
                            style={{
                              ...pageStyles.scoreBarFill,
                              width: `${hyp.score * 100}%`,
                            }}
                          />
                        </div>
                        <span style={pageStyles.metricValue}>{hyp.score.toFixed(2)}</span>
                      </div>
                      <div style={pageStyles.metric}>
                        <span style={pageStyles.metricLabel}>Confidence</span>
                        <span style={pageStyles.metricValue}>{hyp.confidence.toFixed(2)}</span>
                      </div>
                    </div>

                    {hyp.causal_chain.length > 0 && (
                      <div style={pageStyles.chain}>
                        <span style={pageStyles.chainLabel}>Causal chain</span>
                        <div style={pageStyles.steps}>
                          {hyp.causal_chain.map((step, i) => (
                            <div key={i} style={pageStyles.step}>
                              {i + 1}. {step}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    <div style={pageStyles.tags}>
                      {hyp.assumptions.length > 0 && (
                        <span style={pageStyles.tag}>
                          Assumptions: {hyp.assumptions.join(", ")}
                        </span>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

const pageStyles: Record<string, React.CSSProperties> = {
  container: { padding: 24, color: "var(--text)", fontFamily: "system-ui, sans-serif" },
  sectionGroup: { marginBottom: 32 },
  sectionTitle: { margin: "0 0 12px", fontSize: 1.1, color: "var(--muted)", fontFamily: "var(--mono)", textTransform: "uppercase", letterSpacing: "0.05em" },
  cards: { display: "grid", gap: 14, marginTop: 18 },
  hypothesisCard: {
    border: "1px solid var(--border-strong)",
    borderRadius: 8,
    padding: 16,
    background: "var(--surface)",
  },
  cardHead: { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 },
  cardTitle: { margin: 0, fontSize: 1.1 },
  rankBadge: {
    padding: "2px 8px",
    border: "1px solid var(--border)",
    borderRadius: 999,
    fontSize: 0.75,
    fontFamily: "var(--mono)",
    color: "var(--muted)",
  },
  cardSummary: { margin: "0 0 12px", color: "var(--muted)", fontSize: 0.9 },
  scoreRow: { display: "flex", gap: 12, marginBottom: 12 },
  metric: { display: "flex", flexDirection: "column", gap: 2, minWidth: 90 },
  metricLabel: { fontSize: 0.72, fontFamily: "var(--mono)", color: "var(--faint)", textTransform: "uppercase" },
  metricValue: { fontSize: 1, fontWeight: 650, fontFamily: "var(--mono)" },
  scoreBar: { width: "100%", height: 6, background: "var(--surface-raised)", borderRadius: 3, overflow: "hidden", marginTop: 4 },
  scoreBarFill: { height: "100%", background: "var(--primary)", borderRadius: 3, transition: "width 0.3s ease" },
  chain: { marginBottom: 10 },
  chainLabel: { fontSize: 0.72, fontFamily: "var(--mono)", color: "var(--faint)", textTransform: "uppercase", marginBottom: 6 },
  steps: { display: "flex", gap: 6, flexWrap: "wrap" },
  step: {
    padding: "4px 8px",
    border: "1px solid var(--border)",
    borderRadius: 4,
    fontSize: 0.82,
    color: "var(--text)",
    background: "var(--surface-raised)",
  },
  tags: { display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 },
  tag: {
    padding: "3px 8px",
    border: "1px solid var(--border)",
    borderRadius: 4,
    fontSize: 0.75,
    fontFamily: "var(--mono)",
    color: "var(--amber)",
  },
  tagPreliminary: {
    padding: "3px 8px",
    border: "1px solid var(--amber)",
    borderRadius: 4,
    fontSize: 0.75,
    fontFamily: "var(--mono)",
    color: "var(--amber)",
  },
  tagRejected: {
    padding: "3px 8px",
    border: "1px solid var(--red)",
    borderRadius: 4,
    fontSize: 0.75,
    fontFamily: "var(--mono)",
    color: "var(--red)",
  },
};
