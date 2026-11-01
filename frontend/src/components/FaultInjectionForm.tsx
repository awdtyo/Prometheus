import { useState } from "react";

import {
  useScenario,
  useInjectFault,
  ApiError,
  problemFromError,
} from "../api/client";
import type { FaultConfig, FaultOptionResponse } from "../types/api";

interface Props {
  scenarioId: string;
}

export function FaultInjectionForm({ scenarioId }: Props) {
  const { data: scenario, isLoading: loading } = useScenario(scenarioId);
  const { inject, isLoading: injecting } = useInjectFault(scenarioId);

  const [form, setForm] = useState<FaultConfig>({
    fault_type: "power_loss",
    target_subsystem: "",
    start_time: "",
    duration_seconds: 120,
    magnitude: 40,
    parameters: {},
  });
  const [submitted, setSubmitted] = useState<{ preview: boolean; fault_config: FaultConfig; effective_start_time: string; effective_end_time: string } | null>(null);
  const [serverError, setServerError] = useState<{ status: number; code: string | null; detail: string } | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const faultTypes = scenario?.fault_options.map((o: FaultOptionResponse) => o.fault_type) ?? [];
  const selectedOption = scenario?.fault_options.find((o: FaultOptionResponse) => o.fault_type === form.fault_type);
  const targetSubsystems = selectedOption?.target_subsystems ?? [];

  const handleChange = (key: string, value: unknown) => {
    setServerError(null);
    setFieldErrors({});
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const validate = (): boolean => {
    const next: Record<string, string> = {};
    if (!form.fault_type) next.fault_type = "Fault type is required.";
    if (!form.target_subsystem) next.target_subsystem = "Target subsystem is required.";
    if (!form.start_time) next.start_time = "Start time is required.";
    else if (isNaN(Date.parse(form.start_time))) next.start_time = "Start time must be a valid UTC timestamp.";
    if (!form.duration_seconds || form.duration_seconds <= 0) next.duration_seconds = "Duration must be greater than 0.";
    if (form.magnitude == null || form.magnitude < 0) next.magnitude = "Magnitude must be non-negative.";
    if (form.parameters !== undefined) {
      try {
        JSON.stringify(form.parameters);
      } catch {
        next.parameters = "Parameters must be valid JSON.";
      }
    }
    setFieldErrors(next);
    return Object.keys(next).length === 0;
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!validate()) return;
    setServerError(null);
    inject(form).then(
      (preview) => {
        setSubmitted(preview);
      },
      (err) => {
        setSubmitted(null);
        if (err instanceof ApiError) {
          setServerError(problemFromError(err));
        } else {
          setServerError({ status: 0, code: null, detail: err instanceof Error ? err.message : String(err) });
        }
      },
    );
  };

  if (loading) return <div style={formStyles.hint}>Loading scenario fault options…</div>;
  if (!scenario) return null;

  return (
    <section style={formStyles.section}>
      <h3 style={formStyles.title}>Fault injection</h3>
      <p style={formStyles.sub}>
        Validate a fault against scenario <strong>{scenario.id}</strong> and preview its effect.
      </p>

      <form onSubmit={handleSubmit} style={formStyles.form}>
        <div style={formStyles.grid}>
          <Field
            label="Fault type"
            value={form.fault_type}
            options={faultTypes}
            onChange={(v) => handleChange("fault_type", v)}
            error={fieldErrors.fault_type}
          />
          <Field
            label="Target subsystem"
            value={form.target_subsystem}
            options={targetSubsystems}
            onChange={(v) => handleChange("target_subsystem", v)}
            error={fieldErrors.target_subsystem}
          />
          <Field
            label="Start time (UTC)"
            type="text"
            value={form.start_time}
            placeholder="2026-10-30T12:01:00Z"
            onChange={(v) => handleChange("start_time", v)}
            error={fieldErrors.start_time}
          />
          <Field
            label="Duration (seconds)"
            type="number"
            value={String(form.duration_seconds ?? "")}
            onChange={(v) => handleChange("duration_seconds", Number(v))}
            error={fieldErrors.duration_seconds}
          />
          <Field
            label="Magnitude"
            type="number"
            value={String(form.magnitude ?? "")}
            onChange={(v) => handleChange("magnitude", Number(v))}
            error={fieldErrors.magnitude}
          />
        </div>

        {serverError && (
          <div style={formStyles.serverError}>
            <p>Server error ({serverError.status} {serverError.code || "error"}):</p>
            <pre>{serverError.detail}</pre>
          </div>
        )}

        <button
          type="submit"
          disabled={injecting}
          style={formStyles.submit}
        >
          {injecting ? "Validating…" : "Validate & preview injection"}
        </button>
      </form>

      {submitted && (
        <div style={formStyles.preview}>
          <h4>Injection preview</h4>
          <p>
            <strong>injection_id:</strong> {submitted.fault_config ? "" : ""}
          </p>
          <pre>{JSON.stringify(submitted, null, 2)}</pre>
        </div>
      )}
    </section>
  );
}

interface FieldProps {
  label: string;
  value: string;
  options?: string[];
  type?: string;
  placeholder?: string;
  onChange: (v: string | number) => void;
  error?: string;
}

function Field({ label, value, options, type = "text", placeholder, onChange, error }: FieldProps) {
  const handleChange = (event: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>) => {
    onChange(event.target.value);
  };
  return (
    <div style={formStyles.field}>
      <label style={formStyles.label}>{label}</label>
      {options ? (
        <select value={value} onChange={handleChange} style={formStyles.select}>
          <option value="">— select —</option>
          {options.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      ) : (
        <input type={type} value={value} placeholder={placeholder} onChange={handleChange} style={formStyles.input} />
      )}
      {error && <span style={formStyles.fieldError}>{error}</span>}
    </div>
  );
}

const formStyles: Record<string, React.CSSProperties> = {
  section: {
    marginTop: 24,
    padding: 16,
    border: "1px solid var(--border)",
    borderRadius: 8,
    background: "var(--surface-raised)",
  },
  title: { margin: "0 0 4px", fontSize: 1.1 },
  sub: { margin: "0 0 14px", color: "var(--muted)", fontSize: 0.85 },
  hint: { color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 0.85 },
  form: { display: "flex", flexDirection: "column", gap: 12 },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 12 },
  field: { display: "flex", flexDirection: "column", gap: 6 },
  label: { fontSize: 0.78, fontFamily: "var(--mono)", color: "var(--faint)" },
  select: { padding: "6px 8px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: 0.85 },
  input: { padding: "6px 8px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: 0.85 },
  fieldError: { color: "var(--red)", fontSize: 0.78, fontFamily: "var(--mono)" },
  serverError: {
    marginTop: 10,
    padding: 10,
    background: "rgba(255, 107, 107, 0.1)",
    border: "1px solid var(--red)",
    color: "var(--red)",
    fontFamily: "var(--mono)",
    fontSize: 0.8,
  },
  preview: {
    marginTop: 12,
    padding: 10,
    border: "1px solid var(--border)",
    borderRadius: 6,
    background: "rgba(69, 212, 131, 0.1)",
  },
  submit: {
    padding: "8px 14px",
    background: "var(--amber)",
    color: "#161006",
    border: "none",
    borderRadius: 6,
    fontWeight: 650,
    cursor: "pointer",
    alignSelf: "flex-start",
  },
};
