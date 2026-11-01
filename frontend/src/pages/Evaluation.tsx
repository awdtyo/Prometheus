import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

import { emptyEvaluationMetrics, getEvaluation } from "../api/client";
import { Loading } from "../components/Loading";
import type { EvaluationMetrics } from "../types/api";

const METRIC_FIELDS: (keyof EvaluationMetrics)[] = [
  "root_cause_accuracy",
  "fault_localization_accuracy",
  "causal_chain_accuracy",
  "evidence_coverage",
  "temporal_ordering_accuracy",
  "contradiction_handling",
  "unsupported_claim_rate",
  "runtime_seconds",
  "evidence_weight",
  "consistency_weight",
  "coverage_weight",
  "contradiction_penalty",
];

const LABELS: Record<keyof EvaluationMetrics, string> = {
  root_cause_accuracy: "Root cause accuracy",
  fault_localization_accuracy: "Fault localization accuracy",
  causal_chain_accuracy: "Causal chain accuracy",
  evidence_coverage: "Evidence coverage",
  temporal_ordering_accuracy: "Temporal ordering accuracy",
  contradiction_handling: "Contradiction handling",
  unsupported_claim_rate: "Unsupported claim rate",
  runtime_seconds: "Runtime (s)",
  evidence_weight: "Evidence weight",
  consistency_weight: "Consistency weight",
  coverage_weight: "Coverage weight",
  contradiction_penalty: "Contradiction penalty",
};

const COLORS = [
  "#f0a52b",
  "#45d483",
  "#ff6b6b",
  "#3aa9ff",
  "#c38d9e",
  "#9aa5b1",
  "#f0a52b",
  "#45d483",
  "#ff6b6b",
  "#3aa9ff",
  "#c38d9e",
  "#9aa5b1",
];

export function EvaluationPage() {
  const [scenarioId] = (() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("scenario") ?? "battery_failure";
  })();

  const [mode, setMode] = useState<"fake" | "real">("fake");
  const [metrics, setMetrics] = useState<Record<string, number> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);
    getEvaluation(scenarioId, mode)
      .then((data) => {
        if (!cancelled) {
          setMetrics(data);
          setIsLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err);
          setIsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [scenarioId, mode]);

  const metricsData = metrics ?? emptyEvaluationMetrics();
  const chartData = METRIC_FIELDS.map((key) => ({
    name: LABELS[key],
    value: metricsData[key],
  }));

  if (isLoading) return <Loading />;
  if (error) {
    return (
      <div style={pageStyles.container}>
        <h1>Evaluation Dashboard</h1>
        <p>Unable to load evaluation metrics.</p>
        <p>{error instanceof Error ? error.message : String(error)}</p>
      </div>
    );
  }

  const isFake = mode === "fake";

  return (
    <div style={pageStyles.container}>
      <h1>Evaluation Dashboard</h1>
      <div style={pageStyles.modeBar}>
        <span style={pageStyles.modeLabel}>LLM mode:</span>
        <select
          value={mode}
          onChange={(e) => setMode((e.target.value as "fake" | "real") || "fake")}
          style={pageStyles.modeSelect}
        >
          <option value="fake">Fake (offline, plumbing test)</option>
          <option value="real">Real (live Groq LLM)</option>
        </select>
        {isFake && (
          <span style={pageStyles.fakeNotice}>
            ⚠ Fake-LLM numbers only test the plumbing — they are not an
            assessment of root-cause quality.
          </span>
        )}
      </div>

      <div style={pageStyles.tableWrap}>
        <table style={pageStyles.table}>
          <thead>
            <tr>
              <th style={pageStyles.th}>Metric</th>
              <th style={pageStyles.th}>Value</th>
            </tr>
          </thead>
          <tbody>
            {METRIC_FIELDS.map((key) => (
              <tr key={key} style={pageStyles.tr}>
                <td style={pageStyles.td}>{LABELS[key]}</td>
                <td style={pageStyles.tdValue}>{Number(metricsData[key]).toFixed(3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={pageStyles.chartWrap}>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={chartData} layout="vertical" margin={{ left: 140, right: 24, top: 24, bottom: 24 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <YAxis dataKey="name" type="category" width={140} tick={{ fontSize: 11 }} />
            <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 11 }} />
            <Tooltip />
            <Bar dataKey="value" radius={[4, 4, 4, 4]}>
              {chartData.map((_entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

const pageStyles: Record<string, React.CSSProperties> = {
  container: { padding: 24, color: "var(--text)", fontFamily: "system-ui, sans-serif" },
  modeBar: {
    display: "flex",
    alignItems: "center",
    gap: 16,
    marginBottom: 24,
    padding: 16,
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 8,
  },
  modeLabel: { fontSize: 0.85, fontFamily: "var(--mono)", color: "var(--muted)", marginRight: 8 },
  modeSelect: { padding: "6px 10px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: 0.85 },
  fakeNotice: {
    marginLeft: 16,
    fontSize: 0.8,
    fontFamily: "var(--mono)",
    color: "var(--accent-foreground)",
    background: "rgba(240, 165, 43, 0.1)",
    padding: "6px 10px",
    borderRadius: 4,
    border: "1px solid var(--accent)",
  },
  tableWrap: { overflowX: "auto", marginBottom: 24 },
  table: { width: "100%", borderCollapse: "collapse" },
  th: {
    textAlign: "left",
    padding: "8px 10px",
    borderBottom: "1px solid var(--border)",
    fontSize: 0.8,
    fontFamily: "var(--mono)",
    color: "var(--faint)",
    textTransform: "uppercase",
  },
  tr: { borderBottom: "1px solid var(--border)" },
  td: { padding: "8px 10px", fontSize: 0.9 },
  tdValue: {
    fontFamily: "var(--mono)",
    fontSize: 0.9,
    color: "var(--text)",
  },
  chartWrap: { marginTop: 20 },
};
