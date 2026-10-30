/* =============================================================================
   Custom React Flow Node Components
   -------------------------------------------------------
   Distinguishes node types with consistent shapes and colors.
   ============================================================================= */

import React from "react";
import { Node, addEdge } from "react-flow-renderer";

/* -------------------------------------------------------
   Node type colors matching the design system
   ------------------------------------------------------- */

const NODE_COLORS = {
  observation: "#63b3ed",       // cyan blue
  mission_event: "#a855f7",     // purple  
  subsystem: "#f472b6",         // pink/amber
  hypothesis: "#f6ad55",        // amber
  mission_failure: "#e5e7eb",   // gray (neutral for failure)
};

const NODE_BORDER_COLORS = {
  observation: "#63b3ed",
  mission_event: "#a855f7",
  subsystem: "#f472b6",
  hypothesis: "#f6ad55",
  mission_failure: "#9ca3af",
};

const NODE_SHAPES = {
  observation: "ellipse",
  mission_event: "ellipse",
  subsystem: "rectangle",
  hypothesis: "diamond",
  mission_failure: "rectangle rounded",
};

/* -------------------------------------------------------
   Custom Node component
   ------------------------------------------------------- */

type NodeType = "observation" | "mission_event" | "subsystem" | "hypothesis" | "mission_failure";

interface CustomNodeProps {
  node: {
    id: string;
    type: NodeType;
    label: string;
    timestamp?: string;
    evidence_count?: number;
    confidence?: number;
    metadata?: Record<string, unknown>;
  };
  onClick?: (nodeId: string) => void;
  onConnect?: (edge: { id: string; source: string; target: string }) => void;
}

export function CustomNode({
  node,
  onClick,
  onConnect,
}: CustomNodeProps) {
  const nodeType = node.type;
  const color = NODE_COLORS[nodeType] || NODE_COLORS.subsystem;
  const borderColor = NODE_BORDER_COLORS[nodeType] || NODE_BORDER_COLORS.subsystem;
  const shape = NODE_SHAPES[nodeType] || NODE_SHAPES.subsystem;
  const timestamp = node.timestamp ? ` @ ${new Date(node.timestamp).toLocaleTimeString()}` : "";
  const evidenceBadge = node.evidence_count > 0 ? ` (${node.evidence_count} evidence)` : "";
  const confBadge = node.confidence !== undefined && node.confidence > 0 ? ` • conf: ${node.confidence.toFixed(2}` : "";

  // Render different shapes
  if (shape === "diamond") {
    return (
      <div
        className="flow-node diamond-node"
        style={{
          width: 120,
          height: 80,
          backgroundColor: color,
          borderColor: borderColor,
        }}
        onClick={() => onClick?.(node.id)}
        title={node.label}
      >
        <div className="flow-node-content">
          <div className="node-label">{node.label}</div>
          <div className="node-meta">
            {timestamp}{evidenceBadge}{confBadge}
          </div>
        </div>
      </div>
    );
  }

  if (shape === "rectangle rounded") {
    return (
      <div
        className="flow-node failure-node"
        style={{
          width: 140,
          height: 60,
          backgroundColor: color,
          borderColor: borderColor,
        }}
        onClick={() => onClick?.(node.id)}
        title={node.label}
      >
        <div className="flow-node-content">
          <div className="node-label">{node.label}</div>
          <div className="node-meta">
            {timestamp}{evidenceBadge}
          </div>
        </div>
      </div>
    );
  }

  // Default: ellipse for observation and mission_event
  return (
    <div
      className="flow-node ellipse-node"
      style={{
        width: 130,
        height: 60,
        backgroundColor: color,
        borderColor: borderColor,
      }}
      onClick={() => onClick?.(node.id)}
      title={node.label}
    >
      <div className="flow-node-content">
        <div className="node-label">{node.label}</div>
        <div className="node-meta">
          {timestamp}{evidenceBadge}{confBadge}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------
   Diamond shape CSS (inline for the demo)
   ------------------------------------------------------- */

// Diamond shape using CSS transform
// The actual shape is achieved with width/height and border-radius animation

.diamond-node {
  position: relative;
  transform: rotate(45deg);
  transform-origin: center center;
  background-color: #fff;
  .flow-node-content {
    transform: rotate(-45deg);
    padding: 4px 8px;
  }
  .node-label {
    transform: rotate(-45deg);
    font-weight: 600;
    font-size: 0.78rem;
  }
  .node-meta {
    transform: rotate(-45deg);
    font-size: 0.66rem;
    color: #fff;
  }
}

.failure-node {
  border-radius: 8px;
  .flow-node-content {
    padding: 8px;
  }
  .node-label {
    font-weight: 600;
    font-size: 0.82rem;
  }
  .node-meta {
    font-size: 0.7rem;
    color: #374151;
  }
}

.ellipse-node {
  border-radius: 50%;
  .flow-node-content {
    padding: 12px 14px;
  }
  .node-label {
    font-weight: 600;
    font-size: 0.88rem;
  }
  .node-meta {
    font-size: 0.74rem;
    color: #fff;
  }
}