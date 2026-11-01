import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { Node } from "@xyflow/react";

import { ReactFlow, Background, Controls } from "@xyflow/react";
import "@xyflow/react/dist/base.css";

import { getGraph } from "../api/client";
import { useScenario as useScenarioDetail } from "../api/client";
import type { GraphNode } from "../types/api";
import type { SubsystemResponse } from "../types/api";

export function CausalGraphPage() {
  const [searchParams] = useSearchParams();
  const investigationId = searchParams.get("inv") || null;
  const [selected, setSelected] = useState<GraphNode | null>(null);

  const { data: scenario } = useScenarioDetail(investigationId ? investigationId : null);
  const subsystems: SubsystemResponse[] = scenario?.subsystems ?? [];

  const [graph, setGraph] = useState<{ nodes: any[]; edges: any[] } | null>(null);

  useEffect(() => {
    if (!investigationId) {
      setGraph(null);
      return;
    }
    getGraph(investigationId)
      .then((g) => setGraph(g as any))
      .catch(() => setGraph(null));
  }, [investigationId]);

  const nodes: GraphNode[] = graph?.nodes.map((n) => ({
    id: n.node_id,
    label: n.label,
    type: n.node_type as any,
    subsystem: (n.metadata as Record<string, any> | undefined)?.subsystem,
    timestamp: n.timestamp,
    x: 0,
    y: 0,
    metadata: n.metadata,
  })) ?? [];

  const edges: { id: string; source: string; target: string; relationship_type: string; confidence: number; dashed: boolean; metadata: Record<string, any> }[] = graph?.edges.map((e) => ({
    id: e.edge_id,
    source: e.source,
    target: e.target,
    relationship_type: e.relationship_type,
    confidence: e.confidence,
    dashed: e.confidence < 0.5 || !(e.metadata as Record<string, any> | undefined)?.spec_allowed,
    metadata: e.metadata,
  })) ?? [];

  const subsystemRows = subsystems.map((s, i) => ({ id: s.id, y: i }));
  const rowFor = (subsystem: string | null) => {
    if (!subsystem) return null;
    const found = subsystemRows.find((r) => r.id === subsystem);
    return found ? found.y : null;
  };

  const allTimes = nodes
    .map((n) => (n.metadata as Record<string, any> | undefined)?.timestamp ? new Date((n.metadata as Record<string, any>).timestamp).getTime() : null)
    .filter((t) => t !== null) as number[];
  const tMin = allTimes.length ? Math.min(...allTimes) : Date.now();
  const tMax = allTimes.length ? Math.max(...allTimes) : Date.now();
  const span = tMax - tMin || 1;
  const width = 760;
  const xFor = (timestamp: string | null) => {
    if (!timestamp) return 60;
    const t = new Date(timestamp).getTime();
    return 60 + ((t - tMin) / span) * (width - 120);
  };

  nodes.forEach((node) => {
    const row = rowFor(node.subsystem as unknown as string | null);
    node.y = row != null ? 40 + row * 70 : 40;
    node.x = xFor((node.timestamp as unknown as string | null));
  });

  const flowNodes: Node<{ graphNode: GraphNode }>[] = nodes.map((n) => ({
    id: n.id,
    position: { x: n.x, y: n.y },
    data: { label: n.label, graphNode: n },
    style: nodeStyles[n.type as any],
  }));

  const flowEdges = edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    style: {
      stroke: e.confidence < 0.5 || e.dashed ? "var(--faint)" : "var(--amber)",
      strokeWidth: Math.max(1, e.confidence * 4),
      strokeDasharray: e.dashed || e.confidence < 0.5 ? "6 4" : undefined,
    },
  }));

  return (
    <div style={pageStyles.wrap}>
      <div style={pageStyles.toolbar}>
        <h2 style={pageStyles.title}>Causal Graph</h2>
        <p style={pageStyles.hint}>
          Nodes laid out by time (x) and subsystem (y). Edge width by confidence; dashed =
          low confidence or spec-forbidden. Click a node for details.
        </p>
        {!investigationId && (
          <p style={pageStyles.hint}>
            Open an investigation from <a href="/">Scenarios</a> to view its graph.
          </p>
        )}
      </div>

      <div style={pageStyles.graphArea}>
        {!investigationId ? (
          <div style={pageStyles.empty}>Open an investigation to view its graph.</div>
        ) : (
          <ReactFlow
            nodes={flowNodes}
            edges={flowEdges}
            onNodeClick={(event, node) => {
              event.preventDefault();
              setSelected(node.data.graphNode);
            }}
            onPaneClick={() => setSelected(null)}
            fitView
          >
            <Controls />
            <Background />
          </ReactFlow>
        )}
      </div>

      {selected && <SidePanel node={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function SidePanel({ node, onClose }: { node: GraphNode; onClose: () => void }) {
  return (
    <aside style={pageStyles.panel}>
      <button style={pageStyles.close} onClick={onClose}>×</button>
      <h3 style={pageStyles.panelTitle}>Node details</h3>
      <p style={pageStyles.panelRow}><strong>Id:</strong> {node.id}</p>
      <p style={pageStyles.panelRow}><strong>Type:</strong> {node.type}</p>
      {node.subsystem && <p style={pageStyles.panelRow}><strong>Subsystem:</strong> {node.subsystem}</p>}
      {node.timestamp && <p style={pageStyles.panelRow}><strong>Time:</strong> {node.timestamp}</p>}
      {Object.keys(node.metadata).length > 0 && (
        <>
          <p style={pageStyles.panelRow}><strong>Metadata:</strong></p>
          <pre style={pageStyles.panelMeta}>{JSON.stringify(node.metadata, null, 2)}</pre>
        </>
      )}
    </aside>
  );
}

const nodeStyles: Record<string, React.CSSProperties> = {
  subsystem: { fill: "var(--amber)", color: "#161006", stroke: "var(--border-strong)" },
  event: { fill: "var(--surface-raised)", color: "var(--text)", stroke: "var(--border)" },
};

const pageStyles: Record<string, React.CSSProperties> = {
  wrap: { padding: 24, color: "var(--text)", fontFamily: "system-ui, sans-serif", display: "flex", gap: 16 },
  toolbar: { flex: "0 0 260px", flexShrink: 0, paddingRight: 16, borderRight: "1px solid var(--border)" },
  title: { margin: "0 0 8px", fontSize: 1.25 },
  hint: { margin: "0 0 14px", fontSize: 0.85, color: "var(--muted)", lineHeight: 1.5 },
  graphArea: { flex: 1, minHeight: 560, position: "relative", background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 },
  empty: { padding: 40, color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 0.9 },
  panel: {
    position: "absolute",
    right: 0,
    top: 0,
    bottom: 0,
    width: 300,
    padding: 20,
    borderLeft: "1px solid var(--border)",
    background: "var(--surface)",
    overflowY: "auto",
  },
  close: {
    position: "absolute",
    top: 12,
    right: 12,
    background: "transparent",
    border: "none",
    color: "var(--muted)",
    fontSize: 1.4,
    cursor: "pointer",
    lineHeight: 1,
  },
  panelTitle: { margin: "10px 0 10px", fontSize: 1.1 },
  panelRow: { margin: "0 0 8px", fontSize: 0.9 },
  panelMeta: { margin: 0, fontFamily: "var(--mono)", fontSize: 0.78, color: "var(--muted)", whiteSpace: "pre-wrap", background: "var(--surface-raised)", padding: 8, borderRadius: 4 },
};
