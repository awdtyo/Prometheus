import type { GraphNode, GraphEdge, RelationshipType, NodeType } from "../types/domain";
import type { TimelineEvent } from "../types/api";
import type { SubsystemResponse } from "../types/api";

/* =============================================================================
   Build a causal/temporal graph from live API data.
   
   The mock backend exposes no dedicated graph endpoint (see "Backend mismatches"),
   so this derives nodes and edges from the investigation timeline plus the
   scenario's subsystem definitions. Nothing here simulates or infers causality
   beyond what the API returns.
   ============================================================================= */

interface BuildOptions {
  events: TimelineEvent[];
  subsystems: SubsystemResponse[];
  width: number;
}

export function buildGraph({ events, subsystems, width }: BuildOptions): {
  nodes: GraphNode[];
  edges: GraphEdge[];
} {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];

  // Subsystem rows are spread vertically; event time is spread horizontally.
  const subsystemRows = subsystems.map((s, i) => ({ id: s.id, y: i }));
  const rowFor = (subsystem: string | null) => {
    if (!subsystem) return null;
    const found = subsystemRows.find((r) => r.id === subsystem);
    return found ? found.y : null;
  };

  const eventTimes = events.map((e) => new Date(e.timestamp).getTime());
  const tMin = eventTimes.length ? Math.min(...eventTimes) : Date.now();
  const tMax = eventTimes.length ? Math.max(...eventTimes) : Date.now();
  const span = tMax - tMin || 1;
  const xFor = (timestamp: string) => {
    const t = new Date(timestamp).getTime();
    return 60 + ((t - tMin) / span) * (width - 120);
  };

  // Subsystem nodes (static, left column).
  subsystemRows.forEach((row) => {
    const def = subsystems.find((s) => s.id === row.id);
    nodes.push({
      id: `sub:${row.id}`,
      label: def?.name ?? row.id,
      type: "subsystem",
      subsystem: row.id,
      x: 40,
      y: 40 + row.y * 70,
      metadata: { depends_on: def?.depends_on ?? [] },
    });
  });

  // Event nodes (positioned by time and subsystem).
  events.forEach((event) => {
    const row = rowFor(event.subsystem);
    const y = row != null ? 40 + row * 70 : 40;
    nodes.push({
      id: event.event_id,
      label: event.event_type,
      type: "event",
      subsystem: event.subsystem,
      x: xFor(event.timestamp),
      y,
      metadata: event.metadata,
    });
  });

  // Temporal edges between consecutive events (chronological).
  const ordered = [...events].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  ordered.forEach((event, index) => {
    if (index === 0) return;
    const prev = ordered[index - 1];
    edges.push({
      id: `edg:t:${event.event_id}`,
      source: prev.event_id,
      target: event.event_id,
      relationship_type: "TEMPORAL_PRECEDENCE",
      confidence: 0.9,
      dashed: false,
      metadata: {},
    });
  });

  // Subsystem dependency edges.
  subsystems.forEach((sub) => {
    (sub.depends_on ?? []).forEach((dep) => {
      edges.push({
        id: `edg:dep:${sub.id}:${dep}`,
        source: `sub:${dep}`,
        target: `sub:${sub.id}`,
        relationship_type: "SUBSYSTEM_DEPENDENCY",
        confidence: 1.0,
        dashed: false,
        metadata: {},
      });
    });
  });

  return { nodes, edges };
}export type { GraphNode, GraphEdge, RelationshipType, NodeType };
