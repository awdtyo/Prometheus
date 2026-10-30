/* =============================================================================
   Fault Injection Panel Component
   -------------------------------------------------------
   Allows users to configure and submit fault injection scenarios.
   Validates configuration before submitting to the backend.
   ============================================================================= */

import React, { useState } from "react";
import type { FaultType, SubsystemId } from "../types/domain";

/* -------------------------------------------------------
   Fault type options matching the domain enum
   ------------------------------------------------------- */

const FAULT_TYPES: Array<{ value: FaultType; label: string }> = [
  { value: "power_loss", label: "Power Loss" },
  { value: "power_degradation", label: "Power Degradation" },
  { value: "thermal_overheat", label: "Thermal Overheat" },
  { value: "sensor_drift", label: "Sensor Drift" },
  { value: "sensor_failure", label: "Sensor Failure" },
  { value: "communication_loss", label: "Communication Loss" },
  { value: "actuator_failure", label: "Actuator Failure" },
  { value: "software_fault", label: "Software Fault" },
  { value: "unknown", label: "Unknown" },
];

/* -------------------------------------------------------
   Fault injection panel component
   ------------------------------------------------------- */

interface FaultInjectionPanelProps {
  /** Callback when a valid fault config is submitted */
  onSubmit: (config: {
    fault_type: FaultType;
    target_subsystem: SubsystemId;
    target_parameter?: string;
    start_time: string;
    duration_seconds: number;
    magnitude: number;
    parameters?: Record<string, unknown>;
  }) => void;
}

/** Fault injection panel */
export function FaultInjectionPanel({ onSubmit }: FaultInjectionPanelProps) {
  const [faultType, setFaultType] = useState<FaultType>("power_loss");
  const [targetSubsystem, setTargetSubsystem] = useState<SubsystemId>("power");
  const [targetParameter, setTargetParameter] = useState<string>("");
  const [startTime, setStartTime] = useState<string>(new Date().toISOString());
  const [duration, setDuration] = useState<number>(60);
  const [magnitude, setMagnitude] = useState<number>(0.25);
  const [parameters, setParameters] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Valid fault types for each subsystem
  const validSubsystems: Record<FaultType, SubsystemId[]> = {
    power_loss: ["power"],
    power_degradation: ["power"],
    thermal_overheat: ["thermal-control"],
    sensor_drift: ["thermal-control", "power"],
    sensor_failure: ["thermal-control", "power", "battery"],
    communication_loss: ["communication"],
    actuator_failure: ["actuation"],
    software_fault: ["power", "thermal-control", "propulsion"],
    unknown: [],
  };

  // Form validation
  const isValid = {
    faultType: faultType !== "unknown" && faultType !== "",
    targetSubsystem: targetSubsystem !== "",
    targetParameter: targetParameter.length > 0 || isValidForType(faultType),
    startTime: isValidTime(startTime),
    duration: duration > 0,
    magnitude: magnitude >= 0,
  };

  // Check if parameter is valid for the selected fault type
  const isValidForType = (ft: FaultType) => {
    const valid = validSubsystems[ft] || [];
    return valid.includes(targetSubsystem);
  };

  // Handle submit
  const handleSubmit = () => {
    setError(null);
    setLoading(true);

    const config = {
      fault_type: faultType,
      target_subsystem: targetSubsystem,
      target_parameter: targetParameter || undefined,
      start_time: startTime,
      duration_seconds: duration,
      magnitude,
      parameters: Object.keys(parameters).length > 0 ? parameters : undefined,
    };

    onSubmit(config);
  };

  // Handle time input change
  const handleTimeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    // Validate ISO 8601 format
    if (value && !isValidTime(value)) {
      // Revert to last valid value
      setStartTime(new Date().toISOString());
      return;
    }
    setStartTime(value);
  };

  // Format duration input
  const formatDuration = (d: number) => `${d}s`;

  // Format magnitude input
  const formatMagnitude = (m: number) => `${m.toFixed(2)}`;

  return (
    <div className="fault-injection-panel">
      <h3 className="panel-title">Fault Injection Configuration</h3>

      <div className="form-group">
        <label className="form-label">Fault Type</label>
        <select
          className="form-select"
          value={faultType}
          onChange={(e) => setFaultType(e.target.value as FaultType)}
          disabled={loading}
        >
          {FAULT_TYPES.map((ft) => (
            <option key={ft.value} value={ft.value}>
              {ft.label}
            </option>
          ))}
        </select>
        {error && <p className="form-error">{error}</p>}
      </div>

      <div className="form-group">
        <label className="form-label">Target Subsystem</label>
        <select
          className="form-select"
          value={targetSubsystem}
          onChange={(e) => setTargetSubsystem(e.target.value as SubsystemId)}
          disabled={loading}
        >
          {/* Dynamically populate valid subsystems based on fault type */ }
          <option value="power">Power</option>
          <option value="thermal-control">Thermal Control</option>
          <option value="battery">Battery</option>
          <option value="propulsion">Propulsion</option>
          <option value="communication">Communication</option>
          <option value="actuation">Actuation</option>
        </select>
      </div>

      <div className="form-group">
        <label className="form-label">Target Parameter</label>
        <input
          className="form-input"
          value={targetParameter}
          onChange={(e) => setTargetParameter(e.target.value)}
          placeholder="e.g., bus_voltage"
          disabled={loading}
          placeholderDisabled={!isValid.targetParameter}
        />
        {isValid.targetParameter && (
          <small className="form-help">
            Required for {validSubsystems[faultType]?.includes(targetSubsystem)
              ? "this fault type"
              : "the selected configuration"}
          </small>
        )}
      </div>

      <div className="form-group">
        <label className="form-label">Start Time (UTC)</label>
        <input
          className="form-input"
          type="datetime-local"
          value={startTime}
          onChange={handleTimeChange}
          disabled={loading}
        />
      </div>

      <div className="form-group">
        <label className="form-label">Duration (seconds)</label>
        <input
          className="form-input"
          type="number"
          value={duration}
          onChange={(e) => setDuration(Number(e.target.value))}
          min={1}
          disabled={loading}
        />
        <span className="form-help">{formatDuration(duration)}</span>
      </div>

      <div className="form-group">
        <label className="form-label">Magnitude</label>
        <input
          className="form-input"
          type="number"
          step="0.01"
          value={magnitude}
          onChange={(e) => setMagnitude(Number(e.target.value))}
          min={0}
          disabled={loading}
        />
        <span className="form-help">{formatMagnitude(magnitude)}</span>
      </div>

      {isValid.targetParameter && (
        <div className="form-group">
          <label className="form-label">Parameters (optional)</label>
          <input
            className="form-input"
            placeholder="e.g., { { rate: 0.01 } }"
            onChange={(e) => {
              try {
                const parsed = JSON.parse(e.target.value);
                setParameters(parsed);
              } catch {
                // Keep previous valid state
              }
            }}
            placeholder="{ rate: 0.01 }"
          />
        </div>
      )}

      <div className="form-actions">
        <button
          className={`button button--primary ${
            isValid.faultType && isValid.targetSubsystem ? "" : "button--disabled"
          }`}
          onClick={handleSubmit}
          disabled={!isValid.faultType || !isValid.targetSubsystem || loading}
        >
          {loading ? "Running..." : "Inject Fault"}
        </button>
        <button
          className="button button--secondary"
          onClick={() => {
            // Reset form
            setFaultType("power_loss");
            setTargetSubsystem("power");
            setTargetParameter("");
            setStartTime(new Date().toISOString());
            setDuration(60);
            setMagnitude(0.25);
            setParameters({});
            setError(null);
          }}
        >
          Reset
        </button>
      </div>

      {error && <p className="panel-error">{error}</p>}

      {/* Validation hints */}
      <div className="form-hints">
        <strong>Required for valid configuration:</strong>
        <ul>
          <li>Fault type must not be "Unknown"</li>
          <li>Target subsystem must be valid for the selected fault type</li>
          <li>Start time must be a valid UTC timestamp</li>
          <li>Duration must be greater than 0</li>
          <li>Magnitude must be >= 0</li>
        </ul>
      </div>
    </div>
  );
}

/* -------------------------------------------------------
   Form styles (Tailwind-inspired inline classes)
   ------------------------------------------------------- */

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  margin-bottom: 8px;
  font-weight: 600;
  font-size: 0.82rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--faint);
}

.form-select,
.form-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 0.82rem;
  transition: border-color 150ms ease;
}

.form-select:focus,
.form-input:focus {
  outline: none;
  border-color: var(--amber);
}

.form-help {
  font-size: 0.68rem;
  color: var(--muted);
  margin-top: 4px;
}

.form-error {
  color: var(--red);
  font-size: 0.68rem;
  margin-top: 4px;
  min-height: 16px;
}

.panel-error {
  color: var(--red);
  margin-bottom: 16px;
}

.form-hints {
  margin-top: 16px;
  font-size: 0.68rem;
  color: var(--muted);
}

.form-actions {
  display: flex;
  gap: 8px;
  margin-top: 16px;
}

.button--disabled {
  opacity: 0.5;
  pointer-events: none;
}