/* =============================================================================
   Hypothesis Analysis Page
   -------------------------------------------------------
   Displays competing AI-generated hypotheses with evidence tracking,
   contradiction mapping, and ranking metrics. Allows users to explore
   the reasoning chain for each hypothesis and compare them side-by-side.
   ============================================================================= */

import { useEffect, useState } from "react";
import {
  listHypotheses,
  getInvestigation,
} from "../../api/client";
import type {
  HypothesisSummary,
  InvestigationRead,
} from "../../types/api";
import type { MockInvestigation } from "../../types/api";

export function HypothesisAnalysisPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const investigationId = location.pathname.match(/\/hypotheses\/([^/]+)/)?.[1] || "inv_001";

  const [investigation, setInvestigation] = useState<InvestigationRead | null>(null);
  const [hypotheses, setHypotheses] = useState<HypothesisSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load investigation and its hypotheses
  useEffect(() => {
    const controller = new AbortController();

    // Parallel: get the investigation and its hypotheses
    Promise.all([
      getInvestigation(investigationId, controller.signal).then((data) => setInvestigation(data)),
      listHypotheses(investigationId, controller.signal).then((data) => setHypotheses(data)),
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

  if (loading) {
    return (
      <section className="page hypothesis-analysis">
        <div className="page__loading">
          <p>Loading hypotheses...</p>
        </div>
      </section>
    );
  }

  if (!investigation) {
    return (
      <section className="page hypothesis-analysis">
        <div className="page__error">
          <p>Investigation not found: {investigationId}</p>
        </div>
      </section>
    );
  }

  return (
    <section className="page hypothesis-analysis">
      <div className="hypothesis-analysis__header">
        <h2 className="hypothesis-analysis__title">
          Hypothesis Analysis — {investigation.investigation_id}
        </h2>
        <p className="hypothesis-analysis__subtitle">
          {investigation.scenario?.name || "Unknown scenario"}
        </p>
      </div>

      <div className="hypothesis-analysis__compare">
        {hypotheses.map((hyp, idx) => (
          <article
            key={hyp.hypothesis_id}
            className="hypothesis-card"
            style={{ borderLeftColor: idx === 0 ? "--amber" : "--green" }}
          >
            <div className="hypothesis-card__header">
              <span className="hypothesis-card__rank">#{idx + 1}</span>
              <h3 className="hypothesis-card__title">{hyp.title}</h3>
              <p className="hypothesis-card__score">
                score: {hyp.score.toFixed(2)} &nbsp;|&nbsp; confidence:{" "}
                {hyp.confidence.toFixed(2)}
              </p>
            </div>

            <div className="hypothesis-card__causal-chain">
              <strong>Causal chain:</strong>
              <ol>
                {hyp.causal_chain.map((step, i) => (
                  <li key={i}>{step}</li>
                ))}
              </ol>
            </div>

            <div className="hypothesis-card__evidence">
              <strong>Supporting evidence:</strong>
              <ul>
                {hyp.evidence_ids.map((evId) => (
                  <li key={evId}>• {evId}</li>
                ))}
              </ul>
            </div>

            {hyp.contradiction_ids.length > 0 && (
              <div className="hypothesis-card__contradictions">
                <strong>Contradictions:</strong>
                <ul>
                  {hyp.contradiction_ids.map((evId) => (
                    <li key={evId}>• {evId}</li>
                  ))}
                </ul>
              </div>
            )}

            {hyp.assumptions.length > 0 && (
              <div className="hypothesis-card__assumptions">
                <strong>Assumptions:</strong>
                <ul>
                  {hyp.assumptions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            )}

            <div className="hypothesis-card__actions">
              <button className="button button--small button--link">
                View Full Investigation
              </button>
              <button className="button button--small button--link">
                Compare with Others
              </button>
            </div>
          </article>
        ))}
      </div>

      {hypotheses.length === 0 && (
        <div className="empty-state">
          <p>No hypotheses generated for this investigation.</p>
          <button className="button button--primary">
            Run Investigation
          </button>
        </div>
      )}
    </section>
  );
}