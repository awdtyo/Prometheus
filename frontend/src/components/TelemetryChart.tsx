/* =============================================================================
   Telemetry Chart Component
   -------------------------------------------------------
   Displays multiple subsystem telemetry parameters using Recharts.
   Supports:
   - Multiple line series per subsystem
   - Nominal operating ranges (shaded bands)
   - Warning and critical threshold lines
   - Abnormal region highlighting
   - Zoom and time-range selection via brush
   - Reusable across scenarios
   ============================================================================= */

import React, { useState, useRef, useEffect } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Brush,
  BrushX,
  ResponsiveContainer,
  Carousel,
  cellId,
  Tooltip,
  Legend,
} from "recharts";
import type {
  EntityId,
  SubsystemId,
  ParameterName,
  UtcDatetime,
  TelemetryRecord,
  Severity,
} from "../types/domain";
import type { MockObservation } from "../types/api";

/* -------------------------------------------------------
   Props
   ------------------------------------------------------- */

interface TelemetryChartProps {
  /** Telemetry records to display (sorted by timestamp) */
  data: TelemetryRecord[];
  /** Subsystems to show, ordered by preference */
  subsystems: SubsystemId[];
  /** Mission start UTC for reference lines */
  missionStartUtc: UtcDatetime;
  /** Observation markers to display */
  observations?: MockObservation[];
  /** Selected time range (from brush) */
  selectedRange?: [UtcDatetime, UtcDatetime];
  /** Callback when time range changes */
  onRangeChange?: (range: [UtcDatetime, UtcDatetime]) => void;
  /** Callback when an observation is clicked */
  onObservationClick?: (obs: MockObservation) => void;
}

/* -------------------------------------------------------
   Color palette matching the design system
   ------------------------------------------------------- */

const SUBSYSTEM_COLORS: Record<SubsystemId, string> = {
  power: "#63b3ed", // cyan blue
  "thermal-control": "#a855f7", // purple
  battery: "#f472b6", // pink/amber
  propulsion: "#f6ad55", // amber
  "communication": "#38bdf8", // light cyan
  default: "#cbd5e1", // muted gray
};

const SEVERITY_COLORS: Record<Severity, string> = {
  info: "#6b7280",
  low: "#84cc16",
  medium: "#eab308",
  high: "#f87171",
  critical: "#fca5a5",
};

/* -------------------------------------------------------
   Helper: format timestamp for Recharts
   ------------------------------------------------------- */

const formatTime = (date: Date | string | number) => {
  if (typeof date === "string") return new Date(date).getTime();
  if (typeof date === "number") return date;
  return date.getTime();
};

/* -------------------------------------------------------
   TelemetryChart component
   ------------------------------------------------------- */

export function TelemetryChart({
  data,
  subsystems,
  missionStartUtc,
  observations,
  selectedRange,
  onRangeChange,
  onObservationClick,
}: TelemetryChartProps) {
  // Filter data to selected range if provided
  const filteredData = selectedRange
    ? data.filter(
        (record) =>
          new Date(record.timestamp).getTime() >= selectedRange[0].getTime() &&
          new Date(record.timestamp).getTime() <= selectedRange[1].getTime()
      )
    : data;

  // If no data, render empty state
  if (filteredData.length === 0) {
    return (
      <div className="chart-empty-state">
        <p>No telemetry data for the selected time range.</p>
      </div>
    );
  }

  // Get unique parameters per subsystem
  const parametersBySubsystem = subsystems.map((subsystem) => {
    const params = filteredData
      .filter((d) => d.subsystem === subsystem)
      .map((d) => d.parameter);
    // Get unique parameters preserving order
    const unique = [...new Set(params)];
    return { subsystem, parameters: unique.length > 0 ? unique : ["bus_voltage"] };
  });

  // Build series data: for each subsystem, create a line series for each parameter
  const seriesData = parametersBySubsystem.map(({ subsystem, parameters }) => {
    const color = SUBSYSTEM_COLORS[subsystem] || SUBSYSTEM_COLORS.default;
    return {
      name: subsystem,
      color,
      data: parameters.map((param) => ({
        name: param,
        data: filteredData
          .filter((d) => d.subsystem === subsystem && d.parameter === param)
          .map((d) => ({
            name: `${param} (${d.value} ${d.unit})`,
            value: [formatTime(d.timestamp), d.value],
            subsystem,
            parameter: param,
            timestamp: d.timestamp,
            unit: d.unit,
          })),
      })),
    };
  });

  // Extract all unique parameter names for the legend
  const allParameterNames = [...new Set(filteredData.map((d) => d.parameter)))];

  // Compute y-axis domain based on all values
  const allValues = filteredData.map((d) => d.value);
  const minValue = Math.min(...allValues) * 0.9;
  const maxValue = Math.max(...allValues) * 1.1;

  // Extract threshold information from observations if available
  const warningThresholds: number[] = [];
  const criticalThresholds: number[] = [];

  if (observations) {
    observations.forEach((obs) => {
      if (obs.threshold !== null && obs.threshold !== undefined) {
        if (obs.severity === "warning" || obs.severity === "medium") {
          warningThresholds.push(obs.threshold);
        }
        if (obs.severity === "critical" || obs.severity === "high") {
          criticalThresholds.push(obs.threshold);
        }
      }
    });
  }

  return (
    <div className="telemetry-chart">
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={filteredData} margin={{ top: 20, right: 30, left: 0, bottom: 50 }}>
          <XAxis
            dataKey="timestamp"
            type="category"
            angle={-45}
            margin={{ bottom: 15 }}
            tick={({ value }: { value: string }) => new Date(value).toLocaleTimeString()}
            domain={["min", "max"]}
          />

          <YAxis
            domain={["min", "max"]}
            tick={{ fontSize: 10 }}
            label={{ value: "Value", position: "outside", angle: -90 }}
          />

          <Legend verticalAlign="top" height={36} bottom={0} />

          {/* Critical threshold lines */}
          {criticalThresholds.length > 0 && (
            <CartesianGrid strokeDasharray="3 3" stroke="#ff6b6b" />
          )}

          {/* Warning threshold lines */}
          {warningThresholds.length > 0 && (
            <CartesianGrid strokeDasharray="3 3" stroke="#f0a52b" />
          )}

          {/* Nominal range shading - using multiple approach lines */}
          {(() => {
            const nominalMin = minValue;
            const nominalMax = maxValue;
            return (
              <Cell
                key="nominal-range"
                x={cellId("timestamp", new Date(missionStartUtc).getTime())}
                y1={nominalMin}
                y2={nominalMax}
                fill="rgba(69, 212, 131, 0.1)"
              />
            );
          })()}

          {/* Abnormal region shading (highlight areas outside nominal) */}
          {(() => {
            const nominalMin = minValue;
            const nominalMax = maxValue;
            return (
              <Cell
                key="abnormal-region"
                x={cellId("timestamp", new Date(missionStartUtc).getTime())}
                y1={minValue - 5}
                y2={nominalMin}
                fill="rgba(255, 107, 107, 0.15)"
              />
            );
            return (
              <Cell
                key="abnormal-region-upper"
                x={cellId("timestamp", new Date(missionStartUtc).getTime())}
                y1={nominalMax}
                y2={maxValue + 5}
                fill="rgba(255, 107, 107, 0.15)"
              />
            );
          })()}

          {/* Series lines for each parameter per subsystem */}
          {seriesData.map((series, idx) => (
            <Line
              key={idx}
              type="monotone"
              dataKey="value"
              stroke={series.color}
              fill={series.color}
              activeDot={{ r: 8 }}
              dot={true}
              label={false}
            />
          ))}

          {/* Brush for time range selection */}
          <BrushX
            dataKey="timestamp"
            onBrushEnd={onRangeChange}
            height={30}
            tooltip={{ content: "Select range", strokeWidth: 0 }}
            margin={{ bottom: 5 }}
            //@ts-ignore
            stroke="#63b3ed"
            fill="#63b3ed"
            overlayFill="rgba(99, 179, 237, 0.1)"
          />

          {/* Tooltip showing detailed telemetry info */}
          <Tooltip
            item={({ componentRect, element, payload }) => {
              if (!payload || !payload.value) return null;
              const [x, y] = payload.value;
              const record = data.find(
                (d) => new Date(d.timestamp).getTime() === x
              );
              if (!record) return null;
              return (
                <div className="recharts-tooltip-wrapper">
                  <span className="recharts-tooltip-subsystem">
                    {record.subsystem}: {record.parameter}
                  </span>
                  <span className="recharts-tooltip-value">
                    {record.value} {record.unit}
                  </span>
                  <span className="recharts-tooltip-time">
                    {new Date(record.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              );
            }}
          />
        </LineChart>

        {/* Observation markers overlay */}
        {observations && observations.map((obs) => (
          <g key={obs.observation_id} className="observation-markers">
            {filteredData.map((record) => {
              const recordTime = new Date(record.timestamp).getTime();
              const obsTime = new Date(obs.timestamp).getTime();
              const isWithinRange =
                !selectedRange ||
                (recordTime >= selectedRange[0].getTime() &&
                  recordTime <= selectedRange[1].getTime());

              if (isWithinRange && Math.abs(recordTime - obsTime) < 30000) {
                const severityColor = SEVERITY_COLORS[obs.severity] || "#e5e7eb";
                return (
                  <circle
                    key={`${obs.observation_id}-${record.parameter}`}
                    cx={formatTime(record.timestamp)}
                    cy={record.value}
                    r={6}
                    fill={severityColor}
                    stroke={ "#fff"
                    }
                    strokeWidth={2}
                    onClick={() => onObservationClick?.(obs)}
                    title={obs.description}
                  />
                );
              }
              return null;
            })}
          </g>
        ))}

        {/* Cross-hair for selected point */}
        {selectedRange && (
          <g className="cross-hair">
            <line
              x1={selectedRange[0].getTime()}
              x2={selectedRange[0].getTime()}
              y1={minValue - 10}
              y2={maxValue + 10}
              stroke="#fbbf24"
              strokeDasharray="5 5"
            />
            <line
              x1={selectedRange[1].getTime()}
              x2={selectedRange[1].getTime()}
              y1={minValue - 10}
              y2={maxValue + 10}
              stroke="#fbbf24"
              strokeDasharray="5 5"
            />
          </g>
        )}
      </ResponsiveContainer>

      {/* Parameter legend below chart */}
      <div className="parameter-legend">
        <p className="legend-title">Parameters</p>
        <div className="legend-items">
          {allParameterNames.map((param) => (
            <span
              key={param}
              className="legend-item"
            >
              <span
                className="legend-color"
                style={{ backgroundColor: SUBSYSTEM_COLORS.default }}
              />
              {param}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------
   Empty state when no data is available
   ------------------------------------------------------- */

export function TelemetryEmptyState() {
  return (
    <div className="chart-empty-state">
      <p>No telemetry data available</p>
    </div>
  );
}

/* -------------------------------------------------------
   Error state for chart failures
   ------------------------------------------------------- */

export function TelemetryErrorState({ error }: { error: string }) {
  return (
    <div className="chart-error-state">
      <p>Failed to load telemetry chart: {error}</p>
    </div>
  );
}

/* =============================================================================
   Static analysis: ensure data prop types are correct
   ============================================================================= */

TelemetryChart.propTypes = {
  data: PropTypes.arrayOf(
    PropTypes.shape({
      timestamp: PropTypes.instanceOf(Date).isRequired,
      subsystem: PropTypes.string.isRequired,
      parameter: PropTypes.string.isRequired,
      value: PropTypes.number.isRequired,
      unit: PropTypes.string,
    })
  ).isRequired,
  subsystems: PropTypes.arrayOf(PropTypes.string.isRequired).isRequired,
  missionStartUtc: PropTypes.instanceOf(Date).isRequired,
  observations: PropTypes.arrayOf(
    PropTypes.shape({
      observation_id: PropTypes.string,
      timestamp: PropTypes.instanceOf(Date).isRequired,
      subsystem: PropTypes.string.isRequired,
      observation_type: PropTypes.string.isRequired,
      description: PropTypes.string.isRequired,
      observed_value: PropTypes.number.isRequired,
      threshold: PropTypes.number,
      severity: PropTypes.string.isRequired,
      source_ids: PropTypes.arrayOf(PropTypes.string),
    })
  ),
  selectedRange: PropTypes.arrayOf(PropTypes.instanceOf(Date)),
  onRangeChange: PropTypes.func,
  onObservationClick: PropTypes.func,
};