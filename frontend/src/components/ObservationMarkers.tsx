/* =============================================================================
   Observation Markers Component
   -------------------------------------------------------
   Marks extracted observations on the telemetry chart and provides
   a sidebar summary. Supports:
   - Circular markers on telemetry line at observation timestamps
   - Observation ID, timestamp, subsystem, severity display
   - Click-to-expand detail view
   - Cross-linking to timeline events
   - Reusable across scenarios
   ============================================================================= */

import React from "react";
import type {
  EntityId,
  SubsystemId,
  ParameterName,
  UtcDatetime,
  TelemetryRecord,
  Severity,
} from "../types/domain";
import type { MockObservation } from "../types/api";
import { useMemo } from "react";

/* -------------------------------------------------------
   Props
   ------------------------------------------------------- */

interface ObservationMarkersProps {
  /** Telemetry records to mark on */
  data: TelemetryRecord[];
  /** Observations to display as markers */
  observations: MockObservation[];
  /** Selected time range from telemetry brush */
  selectedRange?: [UtcDatetime, UtcDatetime];
  /** Callback when an observation marker is clicked */
  onObservationClick?: (obs: MockObservation) => void;
}

/* -------------------------------------------------------
   Component
   ------------------------------------------------------- */

export function ObservationMarkers({
  data,
  observations,
  selectedRange,
  onObservationClick,
}: ObservationMarkersProps) {
  // Use memoized computed values for performance
  const markedData = useMemo(() => {
    const marks: Array<{
      timestamp: UtcDatetime;
      observation: MockObservation;
      subsystem: SubsystemId;
      observationType: TypeName;
      severity: Severity;
    }> = [];

    observations.forEach((obs) => {
      const matchingRecord = data.find(
        (record) => record.subsystem === obs.subsystem
      );

      if (matchingRecord) {
        marks.push({
          timestamp: obs.timestamp,
          observation: obs,
          subsystem: obs.subsystem,
          observationType: obs.observation_type,
          severity: obs.severity,
        });
      }
    });

    return marks;
  }, [data, observations]);

  // Filter to selected range if provided
  const visibleMarks = selectedRange
    ? markedData.filter(
        (mark) =>
          new Date(mark.timestamp).getTime() >= selectedRange[0].getTime() &&
          new Date(mark.timestamp).getTime() <= selectedRange[1].getTime()
      )
    : markedData;

  // If no observations, render empty state
  if (visibleMarks.length === 0) {
    return (
      <div className="observation-markers-empty">
        <p>No observations to display</p>
      </div>
    );
  }

  return (
    <div className="observation-markers">
      <h4 className="markers-header">Observation Markers</h4>

      <div className="markers-list">
        {visibleMarks.map((mark) => {
          const severityColor =
            SEVERITY_COLORS[mark.severity] || SEVERITY_COLORS.info;

          return (
            <div
              key={mark.observation.observation_id}
              className="marker-item"
              onClick={() => onObservationClick?.(mark.observation)}
              style={{ cursor: "pointer" }}
            >
              {/* Timestamp circle indicator */}
              <span className="marker-dot" style={{ backgroundColor: severityColor }}>
                {new Date(mark.timestamp).toLocaleTimeString()}
              </span>

              {/* Observation details */}
              <div className="marker-details">
                <strong>{mark.observation.observation_id}</strong>
                <span className="marker-subsystem">
                  {mark.subsystem}
                </span>
                <span className="marker-type">
                  {mark.observationType}
                </span>
              </div>

              {/* Severity badge */}
              <span className="marker-severity" style={{ color: severityColor }}>
                {mark.severity}
              </span>
            </div>
          );
        })}
      </div>

      {/* Empty state when no observations in range */}
      {visibleMarks.length === 0 && selectedRange && (
        <p className="markers-empty">
          No observations in the selected time range
        </p>
      )}
    </div>
  );
}

/* -------------------------------------------------------
   Severity colors for markers (matching design system)
   ------------------------------------------------------- */

const SEVERITY_COLORS: Record<Severity, string> = {
  info: "#6b7280",
  low: "#84cc16",
  medium: "#eab308",
  high: "#f87171",
  critical: "#fca5a5",
};