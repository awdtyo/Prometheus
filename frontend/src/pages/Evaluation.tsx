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

import { emptyEvaluationMetrics } from "../api/client";
import type { EvaluationMetrics } from "../types/api";

const METRIC_FIELDS: (keyof EvaluationMetrics)[] = [
  "root_cause_accuracy",
  "runtime_seconds",
  "evidence_weight",
  "consistency_weight",
  "coverage_weight",
  "contradiction_penalty",
  "fault_localization_accuracy",
  "causal_chain_accuracy",
  "evidence_coverage",
  "temporal_ordering_accuracy",
  "contradiction_handling",
  "unsupported_claim_rate",
];

const LABELS: Record<keyof EvaluationMetrics, string> = {
  root_cause_accuracy: "Root cause accuracy",
  runtime_seconds: "Runtime (s)",
  evidence_weight: "Evidence weight",
  consistency_weight: "Consistency weight",
  coverage_weight: "Coverage weight",
  contradiction_penalty: "Contradiction penalty",
  fault_localization_accuracy: "Fault localization accuracy",
  causal_chain_accuracy: "Causal chain accuracy",
  evidence_coverage: "Evidence coverage",
  temporal_ordering_accuracy: "Temporal ordering accuracy",
  contradiction_handling: "Contradiction handling",
  unsupported_claim_rate: "Unsupported claim rate",
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
  const metrics = emptyEvaluationMetrics();
  const chartData = METRIC_FIELDS.map((key) => ({
    name: LABELS[key],
    value: metrics[key],
  }));

  return (
    <div style={pageStyles.container}>
      <h1>Evaluation Dashboard</h1>
      <p style={pageStyles.note}>
        The mock backend does not expose an evaluation-metrics endpoint yet, so no measured
        values are available. The table below shows the 12-field
        <code>EvaluationMetrics</code> shape per the contract, populated from the empty shape.
        See "Backend mismatches" in the rebuild report.
      </p>

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
                <td style={pageStyles.tdValue}>{Number(metrics[key]).toFixed(3)}</td>
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
  note: { margin: "0 0 16px", color: "var(--muted)", fontSize: 0.85, fontFamily: "var(--mono)" },
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
