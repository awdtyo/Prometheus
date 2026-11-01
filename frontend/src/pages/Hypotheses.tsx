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
        <div style={pageStyles.cards}>
          {ordered.map((hyp) => (
            <article
              key={hyp.hypothesis_id}
              style={{
                border: `1px solid ${hyp.score < 0.4 ? "var(--border)" : "var(--border-strong)"}`,
                borderRadius: 8,
                padding: 16,
                background: hyp.score < 0.4 ? "rgba(30, 34, 44, 0.6)" : "var(--surface)",
                opacity: hyp.score < 0.4 ? 0.7 : 1,
              }}
            >
              <div style={pageStyles.cardHead}>
                <h2 style={pageStyles.cardTitle}>{hyp.title}</h2>
                <span style={pageStyles.rankBadge}>#{ordered.indexOf(hyp) + 1}</span>
              </div>
              <p style={pageStyles.cardSummary}>{hyp.summary}</p>

              <div style={pageStyles.scoreRow}>
                <div style={pageStyles.metric}>
                  <span style={pageStyles.metricLabel}>Score</span>
                  <span style={pageStyles.metricValue}>{(hyp.score * 100).toFixed(0)}%</span>
                </div>
                <div style={pageStyles.metric}>
                  <span style={pageStyles.metricLabel}>Confidence</span>
                  <span style={pageStyles.metricValue}>{(hyp.confidence * 100).toFixed(0)}%</span>
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
                  <span style={pageStyles.tag}>Assumptions: {hyp.assumptions.join(", ")}</span>
                )}
                {hyp.score < 0.4 && <span style={pageStyles.tagRejected}>Rejected (low score)</span>}
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

const pageStyles: Record<string, React.CSSProperties> = {
  container: { padding: 24, color: "var(--text)", fontFamily: "system-ui, sans-serif" },
  cards: { display: "grid", gap: 14, marginTop: 18 },
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
  tagRejected: {
    padding: "3px 8px",
    border: "1px solid var(--red)",
    borderRadius: 4,
    fontSize: 0.75,
    fontFamily: "var(--mono)",
    color: "var(--red)",
  },
};
