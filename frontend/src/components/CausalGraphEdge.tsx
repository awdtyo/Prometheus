/* =============================================================================
   Custom React Flow Edge Components
   -------------------------------------------------------
   Distinguishes observed relationships from proposed causal relationships.
   Uses different line styles for observed vs hypothetical edges.
   Displays timestamps, evidence counts, and confidence only where meaningful.
   ============================================================================= */

import React from "react";
import { Edge } from "react-flow-renderer";

/* -------------------------------------------------------
   Edge relationship types and visual styling
   ------------------------------------------------------- */

type EdgeType = 
  | "TEMPORAL_PRECEDENCE"
  | "SUBSYSTEM_DEPENDENCY" 
  | "OBSERVED_CORRELATION"
  | "CAUSAL_HYPOTHESIS"
  | "CONTRADICTS";

const EDGE_STYLES: Record<EdgeType, {
  stroke: string;
  strokeWidth: number;
  strokeDasharray?: string;
  arrowColor?: string;
}> = {
  TEMPORAL_PRECEDENCE: {
    stroke: "#63b3ed",       // cyan blue - observed temporal
    strokeWidth: 2,
    strokeDasharray: null,
    arrowColor: "#63b3ed",
  },
  SUBSYSTEM_DEPENDENCY: {
    stroke: "#f472b6",       // pink - observed dependency
    strokeWidth: 2,
    strokeDasharray: null,
    arrowColor: "#f472b6",
  },
  OBSERVED_CORRELATION: {
    stroke: "#f6ad55",       // amber - observed correlation
    strokeWidth: 2,
    strokeDasharray: "5 5",  // dashed line for observed
    arrowColor: "#f6ad55",
  },
  CAUSAL_HYPOTHESIS: {
    stroke: "#a855f7",       // purple - hypothesized causal
    strokeWidth: 3,
    strokeDasharray: null,
    arrowColor: "#a855f7",
    // Note: no arrowhead or different style to distinguish from observed
  },
  CONTRADICTS: {
    stroke: "#f87171",       // red - contradiction
    strokeWidth: 2,
    strokeDasharray: "3 3",  // dotted line for contradiction
    arrowColor: "#f87171",
  },
};

/* -------------------------------------------------------
   Custom Edge component
   ------------------------------------------------------- */

interface CustomEdgeProps {
  edge: {
    id: string;
    source: string;
    target: string;
    type: EdgeType;
    label?: string;
    evidence_count?: number;
    confidence?: number;
    timestamp?: string;
    metadata?: Record<string, unknown>;
  };
  onClick?: (edgeId: string) => void;
}

export function CustomEdge({
  edge,
  onClick,
}: CustomEdgeProps) {
  const style = EDGE_STYLES[edge.type] || EDGE_STYLES.TEMPORAL_PRECEDENCE;
  const showEvidence = edge.evidence_count > 0;
  const showConfidence = edge.confidence !== undefined && edge.confidence > 0 && edge.type !== "CONTRADICTS";
  const timestampBadge = edge.timestamp ? ` @ ${new Date(edge.timestamp).toLocaleTimeString()}` : "";
  const evidenceBadge = showEvidence ? ` (${edge.evidence_count} evidence)` : "";
  const confBadge = showConfidence ? ` • conf: ${edge.confidence?.toFixed(2)` : "";

  // For causal hypotheses, use a different arrow style to indicate "proposed" vs "confirmed"
  const arrowhead = edge.type === "CAUSAL_HYPOTHESIS" ? "none" : "block";

  return (
    <Edge
      id={edge.id}
      source={edge.source}
      target={edge.target}
      type={edge.type}
      style={{
        stroke: style.stroke,
        strokeWidth: style.strokeWidth,
        strokeDasharray: style.strokeDasharray,
      }}
      markerEnd={arrowhead}
      data={edge}
      onClick={() => onClick?.(edge.id)}
      title={
        <div className="edge-tooltip">
          <span className="edge-type">
            {edge.type}
          </span>
          {timestampBadge}{evidenceBadge}{confBadge}
        </div>
      }
    />
  );
}

/* =============================================================================
   Edge tooltip styles (inline for the demo)
   ============================================================================= */

.edge-tooltip {
  font-size: 0.68rem;
  .edge-type {
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    font-size: 0.62rem;
  }
}