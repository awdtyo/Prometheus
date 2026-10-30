/* =============================================================================
   Mission Event Timeline Component
   -------------------------------------------------------
   Displays mission events chronologically with severity distinction.
   Supports:
   - Chronological event listing
   - Severity-based styling (info/low/medium/high/critical)
   - Click-to-inspect detail popover
   - Cross-linking to telemetry anomalies
   - Reusable across scenarios
   ============================================================================= */

import React from "react";
import type {
  EntityId,
  SubsystemId,
  TypeName,
  Severity,
  UtcDatetime,
  TimelineEvent,
} from "../types/domain";
import type { MockObservation } from "../types/api";

/* -------------------------------------------------------
   Props
   ------------------------------------------------------- */

interface EventTimelineProps {
  /** Events to display, sorted chronologically */
  events: TimelineEvent[];
  /** Observations to cross-reference */
  observations?: MockObservation[];
  /** Selected time range from telemetry brush */
  selectedRange?: [UtcDatetime, UtcDatetime];
  /** Callback when an event is clicked */
  onEventClick?: (event: TimelineEvent, observation?: MockObservation) => void;
  /** Mission start UTC for context */
  missionStartUtc: UtcDatetime;
}

/* -------------------------------------------------------
   Severity badge colors matching design system
   ------------------------------------------------------- */

const SEVERITY_BADGE_COLORS: Record<Severity, string> = {
  info: "rgba(107, 114, 128, 0.2)",
  low: "rgba(132, 204, 22, 0.2)",
  medium: "rgba(234, 179, 8, 0.2)",
  high: "rgba(248, 113, 113, 0.2)",
  critical: "rgba(252, 165, 165, 0.2)",
};

/* -------------------------------------------------------
   EventTimeline component
   ------------------------------------------------------- */

export function EventTimeline({
  events,
  observations,
  selectedRange,
  onEventClick,
  missionStartUtc,
}: EventTimelineProps) {
  // Sort events chronologically
  const sortedEvents = [...events].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  // If no events, render empty state
  if (sortedEvents.length === 0) {
    return (
      <div className="event-timeline-empty">
        <p>No mission events recorded.</p>
      </div>
    );
  }

  return (
    <div className="event-timeline">
      <h4 className="timeline-header">
        Mission Event Timeline
        <span className="timeline-count">({sortedEvents.length} events)</span>
      </h4>

      <div className="timeline-events">
        {sortedEvents.map((event) => {
          const eventTime = new Date(event.timestamp).getTime();
          const isWithinSelectedRange =
            !selectedRange ||
            (eventTime >= selectedRange[0].getTime() &&
              eventTime <= selectedRange[1].getTime());

          // Find related observations
          const relatedObservations = observations?.filter(
            (obs) =>
              obs.source_ids?.some((src) => src === event.event_id) ||
              (obs.description?.includes(event.event_type ?? "") &&
                Math.abs(new Date(obs.timestamp).getTime() - eventTime) < 60000)
          ) || [];

          // Determine if any related observation is critical
          const hasCriticalObservation =
            relatedObservations.some((obs) => obs.severity === "critical" || obs.severity === "high");

          // Determine badge color
          const badgeColor = SEVERITY_BADGE_COLORS[event.severity] || SEVERITY_BADGE_COLORS.info;
          const badgeBorderColor = event.severity || "info";

          return (
            <div
              key={event.event_id}
              className={`timeline-event ${
                isWithinSelectedRange ? "timeline-event--selected" : ""
              }`}
              onClick={() => onEventClick?.(event, hasCriticalObservation ? relatedObservations[0] : undefined)}
              style={{ cursor: "pointer" }}
            >
              <span className="timeline-event-time">
                {new Date(event.timestamp).toLocaleTimeString()}
              </span>
              <span className="timeline-event-badge" style={{ backgroundColor: badgeColor, borderColor: badgeBorderColor }}>
                {event.severity}
              </span>
              <span className="timeline-event-subsystem">
                {event.subsystem}
              </span>
              <span className="timeline-event-type">
                {event.event_type || "—"}
              </span>
              <span className="timeline-event-desc">
                {event.description}
              </span>
              {relatedObservations.length > 0 && (
                <div className="timeline-event-tooltip">
                  <strong>{relatedObservations.length} observation{s:
                    relatedObservations.length > 1 ? "s" : ""}</strong>
                  {relatedObservations.map((obs) => (
                    <span key={obs.observation_id} className="obs-ref">
                      • {obs.observation_id}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Empty state when no events match selection */}
      {sortedEvents.length > 0 && !isWithinSelectedRange(sortedEvents[0]) && (
        <div className="event-timeline-out-of-range">
          <p>Events outside selected time range</p>
        </div>
      )}
    </div>
  );
}

/* =============================================================================
   Styles (inline for the demo; in production use CSS modules or Tailwind)
   ============================================================================= */

// Timeline event horizontal layout
// Each event is a horizontal block with time on left, details on right
// Badge color indicates severity
// Clickable area shows related observations if any

.EventTimelineEmpty {
  padding: 20px;
  text-align: center;
  color: var(--muted);
}

.TimelineHeader {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 12px;
  font-size: 0.82rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--faint);
}

.TimelineEvents {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.TimelineEvent {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  transition: background 150ms ease;
}

.TimelineEvent:hover {
  background: var(--surface-raised);
}

.TimelineEvent--selected {
  border-color: var(--amber);
  background: rgba(240, 165, 43, 0.1);
}

.TimelineEventBadge {
  flex-shrink: 0;
  width: 24px;
  height: 20px;
  border-radius: 50%;
  font-size: 0.58rem;
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.TimelineEventSubsystem {
  font-size: 0.74rem;
  color: var(--muted);
  margin-left: 8px;
}

.TimelineEventType {
  font-size: 0.7rem;
  color: var(--faint);
  margin-left: 8px;
  text-transform: lowercase;
}

.TimelineEventDesc {
  flex: 1;
  font-size: 0.82rem;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-left: 8px;
}

.TimelineEventTooltip {
  margin-left: 12px;
  font-size: 0.68rem;
  color: var(--muted);
  flex-shrink: 0;
}

.ObservationRef {
  margin-left: 4px;
  font-size: 0.62rem;
  color: var(--faint);
}

.EventTimelineOutOfRange {
  padding: 12px;
  text-align: center;
  color: var(--muted);
  font-size: 0.74rem;
}