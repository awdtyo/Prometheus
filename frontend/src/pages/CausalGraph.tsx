/* =============================================================================
   Temporal Causal Graph Page
   -------------------------------------------------------
   Visualizes how spacecraft subsystem observations and events relate across
   mission time using React Flow with custom nodes and edges.
   
   Features:
   - Node types: Observation, Mission Event, Subsystem, Hypothesis, Mission Failure
   - Edge types: TEMPORAL_PRECEDENCE, SUBSYSTEM_DEPENDENCY, OBSERVED_CORRELATION,
     CAUSAL_HYPOTHESIS, CONTRADICTS
   - Custom-styled nodes/edges distinguishing observed vs hypothetical
   - Pan/zoom, drag, click interactions
   - Filter by subsystem and relationship type
   - Highlight upstream dependencies and downstream affected systems
   - Reset layout and focus on selected hypothesis
   - Clear legend
   - Handles larger node counts with clustering/ grouping
   ============================================================================= */

import React, { useState, useRef, useEffect } from "react";
import {
  Flow,
  Node as RFNode,
  Edge as RFEdge,
  useReactFlow,
  applyNodePosition,
} from "react-flow-renderer";
import type {
  Node as RFNodeType,
  Edge as RFEdgeType,
} from "react-flow-renderer";

import { useLocation, useNavigate } from "react-router-dom";

import { MockInvestigation as MockInv } from "../../types/api";
import { CustomNode } from "./CausalGraphNode";
import { CustomEdge } from "./CausalGraphEdge";

/* =============================================================================
   Mock graph data - supplied for the demo
   In production, this would come from the backend API
   ============================================================================= */

const MOCK_GRAPH = {
  nodes: [
    { id: "sub:power", type: "subsystem", label: "Power", evidence_count: 5, confidence: 0.95 },
    { id: "sub:thermal-control", type: "subsystem", label: "Thermal Control", evidence_count: 3, confidence: 0.88 },
    { id: "sub:battery", type: "subsystem", label: "Battery", evidence_count: 7, confidence: 0.92 },
    { id: "sub:propulsion", type: "subsystem", label: "Propulsion", evidence_count: 2, confidence: 0.75 },
    { id: "evt:voltage_drop", type: "mission_event", label: "Under-voltage alert", evidence_count: 3, confidence: 0.95 },
    { id: "evt:heater_on", type: "mission_event", label: "Heater activated", evidence_count: 2, confidence: 0.87 },
    { id: "obs:bus_voltage", type: "observation", label: "Bus voltage sample", evidence_count: 1, confidence: 0.98, timestamp: "2026-10-30T12:00:30Z" },
    { id: "obs:heater_status", type: "observation", label: "Heater status", evidence_count: 1, confidence: 0.93, timestamp: "2026-10-30T12:00:15Z" },
    { id: "hyp:heater_fault", type: "hypothesis", label: "Stuck heater fault", evidence_count: 5, confidence: 0.82, assumptions: ["Battery SOH nominal"] },
    { id: "fail:power_loss", type: "mission_failure", label: "Power loss event", evidence_count: 0, confidence: 0.0 },
  ],
  edges: [
    { id: "edg:temporal:1", source: "sub:power", target: "evt:voltage_drop", type: "TEMPORAL_PRECEDENCE", evidence_count: 3, confidence: 0.95 },
    { id: "edg:temporal:2", source: "sub:thermal-control", target: "evt:heater_on", type: "TEMPORAL_PRECEDENCE", evidence_count: 2, confidence: 0.88 },
    { id: "edg:obs:1", source: "obs:bus_voltage", target: "evt:voltage_drop", type: "OBSERVED_CORRELATION", evidence_count: 1, confidence: 0.98 },
    { id: "edg:obs:2", source: "obs:heater_status", target: "evt:heater_on", type: "OBSERVED_CORRELATION", evidence_count: 1, confidence: 0.93 },
    { id: "edg:hyp:1", source: "sub:battery", target: "hyp:heater_fault", type: "CAUSAL_HYPOTHESIS", evidence_count: 5, confidence: 0.82 },
    { id: "edg:hyp:2", source: "hyp:heater_fault", target: "fail:power_loss", type: "CAUSAL_HYPOTHESIS", evidence_count: 0, confidence: 0.0 },
    { id: "edg:contr:1", source: "hyp:heater_fault", target: "hyp:heater_fault", type: "CONTRADICTS", evidence_count: 0, confidence: 0.0 }, // self-contradiction placeholder
  ],
};

/* =============================================================================
   Page component
   ============================================================================= */

export function CausalGraphPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const investigationId = location.pathname.match(/\/causal-graph([^/]*)/)?.[1] || "";

  // State for React Flow
  const [nodes, setNodes] = useState<RFNodeType[]>(() => {
    // Transform mock graph nodes to React Flow format
    return MOCK_GRAPH.nodes.map((n) => ({
      id: n.id,
      type: n.type,
      position: { x: 0, y: 0 }, // will be positioned by applyNodePosition
      data: {
        label: n.label,
        evidenceCount: n.evidence_count,
        confidence: n.confidence,
        timestamp: n.timestamp,
        nodeType: n.type,
      },
    });
  });

  const [edges, setEdges] = useState<RFEdgeType[]>(() => {
    // Transform mock graph edges to React Flow format
    return MOCK_GRAPH.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: e.type,
      data: {
        label: e.type,
        evidenceCount: e.evidence_count,
        confidence: e.confidence,
        timestamp: e.timestamp,
        edgeType: e.type,
      },
    });
  });

  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [filteredNodes, setFilteredNodes] = useState<RFNodeType[]>(nodes);
  const [filteredEdges, setFilteredEdges] = useState<RFEdgeType[]>(edges);

  const [subsystemFilter, setSubsystemFilter] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  // Interaction states
  const [dragPosition, setDragPosition] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);

  // Layout state
  const [layoutPositions, setLayoutPositions] = useState<Record<string, { x: number; y: number }>>({});

  // Get the flow instance ref
  const flowRef = useRef<any>(null);

  // Apply initial layout positioning
  useEffect(() => {
    // Position subsystems on left, events in middle, observations/hypotheses/failures on right
    const positionedNodes = [...nodes];
    
    // Group by type and position
    const subsystems = nodes.filter(n => n.type === "subsystem");
    const events = nodes.filter(n => n.type === "mission_event");
    const observations = nodes.filter(n => n.type === "observation");
    const hypotheses = nodes.filter(n => n.type === "hypothesis");
    const failures = nodes.filter(n => n.type === "mission_failure");

    // Position subsystems vertically on left
    subsystems.forEach((node, i) => {
      positionedNodes.find(n => n.id === node.id)!.data!.position = {
        x: 100,
        y: 100 + (i * 150),
      };
    });

    // Position events in middle
    events.forEach((node, i) => {
      positionedNodes.find(n => n.id === node.id)!.data!.position = {
        x: 300,
        y: 100 + (i * 120),
      };
    });

    // Position observations
    observations.forEach((node, i) => {
      positionedNodes.find(n => n.id === node.id)!.data!.position = {
        x: 500,
        y: 50 + (i * 100),
      };
    });

    // Position hypotheses
    hypotheses.forEach((node, i) => {
      positionedNodes.find(n => n.id === node.id)!.data!.position = {
        x: 700,
        y: 100 + (i * 120),
      };
    });

    // Position failure
    failures.forEach((node) => {
      positionedNodes.find(n => n.id === node.id)!.data!.position = {
        x: 900,
        y: 300,
      };
    });

    setLayoutPositions(
      Object.fromEntries(
        positionedNodes.map(n => [n.id, n.data.position as { x: number; y: number }])
      )
    );

    setNodes(positionedNodes);
  }, [nodes]);

  // Filter nodes and edges based on subsystem and type filters
  useEffect(() => {
    let filteredN = nodes;
    let filteredE = edges;

    if (subsystemFilter) {
      // Show nodes that are subsystems or connect to the filtered subsystem
      const filteredSubsystemNodes = nodes.filter(n => 
        n.type === "subsystem" || 
        (n.data.evidenceCount && nodes.some(n2 => n2.type === "subsystem" && n2.id === subsystemFilter))
      );
      filteredN = [...filteredSubsystemNodes];
      
      // Filter edges that involve this subsystem
      filteredE = edges.filter(e => 
        e.source === subsystemFilter || e.target === subsystemFilter
      );
    }

    if (typeFilter) {
      filteredE = edges.filter(e => e.type === typeFilter);
      // Show nodes connected to these edges
      const filteredEdgeIds = new Set(filteredE.map(e => e.id));
      const connectedNodeIds = new Set<string>();
      filteredE.forEach(e => {
        connectedNodeIds.add(e.source);
        connectedNodeIds.add(e.target);
      });
      filteredN = nodes.filter(n => connectedNodeIds.has(n.id));
    }

    setFilteredNodes(filteredN);
    setFilteredEdges(filteredE);
  }, [nodes, edges, subsystemFilter, typeFilter]);

  // Highlight upstream (source) and downstream (target) of selected node
  const highlightUpstream = (nodeId: string) => {
    // Find all edges where this node is the target (downstream)
    // and where this node is the source (upstream)
    // This is a simplified version - real implementation would do BFS/DFS
    setFilteredNodes(prev => 
      prev.map(n => 
        n.id === nodeId 
          ? { ...n, data: { ...n.data, highlighted: true } }
          : n.data.highlighted 
            ? { ...n, data: { ...n.data, highlighted: false } }
            : n
      )
    );
  };

  // Reset all highlights
  const resetHighlights = () => {
    setFilteredNodes(
      nodes.map(n => ({
        ...n,
        data: { ...n.data, highlighted: false },
      }))
    );
    setSelectedNode(null);
    setSelectedEdge(null);
  };

  // Focus on selected hypothesis
  const focusOnHypothesis = (hypothesisId: string) => {
    // Find the hypothesis node and center the view on it
    const hypothesisNode = nodes.find(n => n.id === hypothesisId);
    if (hypothesisNode && flowRef.current) {
      flowRef.current.setNodePosition(hypothesisNode.id, { x: 400, y: 300 });
      setSelectedNode(hypothesisId);
    }
  };

  // Layout clustering for large node counts
  const CLUSTER_THRESHOLD = 50;
  const nodeCount = nodes.length;

  return (
    <div className="causal-graph-page">
      <header className="causal-graph-header">
        <h2 className="header-title">Temporal Causal Graph</h2>
        <div className="header-actions">
          <button
            className="button button--small button--icon"
            onClick={resetHighlights}
            title="Reset highlights"
            aria-label="Reset highlights"
          >
            ✕
          </button>
          <button
            className="button button--small button--icon"
            onClick={() => navigate(`/causal-graph${investigationId}`)}
            title="Reset graph layout"
            aria-label="Reset layout"
          ⟳
          </button>
        </div>
      </header>

      <div className="causal-graph-container">
        {/* Legend */}
        <div className="causal-graph-legend">
          <h4 className="legend-title">Legend</h4>
          <div className="legend-items">
            <div className="legend-item">
              <div className="legend-square subsystem"></div>
              <span>Subsystem</span>
            </div>
            <div className="legend-square observation"></div>
            <span>Observation</span>
            <div className="legend-square event"></div>
            <span>Mission Event</span>
            <div className="legend-square hypothesis"></div>
            <span>Hypothesis</span>
            <div className="legend-square failure"></div>
            <span>Mission Failure</span>
          </div>
          <div className="legend-items" style={{ marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--border)' }}>
            <div className="legend-item">
              <div className="legend-solid"></div>
              <span>Observed relationship (solid)</span>
            </div>
            <div className="legend-item">
              <div className="legend-dashed"></div>
              <span>Observed correlation (dashed)</span>
            </div>
            <div className="legend-item">
              <div className="legend-dotted"></div>
              <span>Contradiction (dotted)</span>
            </div>
            <div className="legend-item">
              <div className="legend-arrow-purple"></div>
              <span>Causal hypothesis (proposed)</span>
            </div>
          </div>
        </div>

        {/* Filter controls */}
        <div className="causal-graph-filters">
          <select
            className="filter-select"
            onChange={(e) => setSubsystemFilter(e.target.value || null)}
            title="Filter by subsystem">
              <option value="">All subsystems</option>
              <option value="sub:power">Power</option>
              <option value="sub:thermal-control">Thermal Control</option>
              <option value="sub:battery">Battery</option>
              <option value="sub:propulsion">Propulsion</option>
            </select>
            <select
              className="filter-select"
              onChange={(e) => setTypeFilter(e.target.value || null)}
              title="Filter by relationship type">
                <option value="">All relationship types</option>
                <option value="TEMPORAL_PRECEDENCE">Temporal Precedence</option>
                <option value="SUBSYSTEM_DEPENDENCY">Subsystem Dependency</option>
                <option value="OBSERVED_CORRELATION">Observed Correlation</option>
                <option value="CAUSAL_HYPOTHESIS">Causal Hypothesis</option>
                <option value="CONTRADICTS">Contradiction</option>
              </select>
          </select>
        </div>

        <Flow
          ref={flowRef}
          nodes={filteredNodes}
          edges={filteredEdges}
          onSelect={({ type, data }) => {
            if (type === "node") {
              setSelectedNode(data.id);
            } else if (type === "edge") {
              setSelectedEdge(data.id);
            }
          }}
          onConnect={({ node, edge }) => {
            // Handle edge creation if needed
          }}
          onNodeClick={({ node }) => {
            setSelectedNode(node.id);
          }}
          onEdgeClick={({ edge }) => {
            setSelectedEdge(edge.id);
          }}
          panBy={dragPosition}
          zoom={1.2}
          fitView
          margin={50}
        >
          {filteredNodes.map((node) => (
            <CustomNode
              key={node.id}
              node={node.data as any}
              onClick={() => {
                // Cycle through interaction states
                if (node.id === selectedNode) {
                  // If already selected, don't deselect immediately - let click details panel handle it
                } else {
                  setSelectedNode(node.id);
                  // Reset other highlights
                  setFilteredNodes(prev =>
                    prev.map(n => ({
                      ...n,
                      data: { ...n.data, highlighted: n.id === selectedNode },
                    }))
                  );
                }
              }}
            />
          ))}

          {filteredEdges.map((edge) => (
            <CustomEdge
              key={edge.id}
              edge={{ ...edge, data: edge.data as any }}
              onClick={() => {
                setSelectedEdge(edge.id);
                // Show edge detail info
                console.log("Edge clicked:", edge);
              }}
            />
          ))}

          {/* Highlight selected node and its connections */}
          {selectedNode && (
            <g className="highlight-connections">
              {filteredEdges.map((edge) => {
                // Highlight edges connected to selected node
                const isConnected = edge.source === selectedNode || edge.target === selectedNode;
                if (isConnected) {
                  // Clone the edge with highlighted style
                  return (
                    <CustomEdge
                      key={edge.id}
                      edge={{ ...edge, data: { ...edge.data, highlighted: true } as any }}
                      style={{
                        ...EDGE_STYLES[edge.type as EdgeType].stroke === "#f87171" 
                          ? { stroke: "#f87171", strokeWidth: 4 }
                          : { stroke: "#63b3ed", strokeWidth: 4 }.
                        strokeDasharray: edge.type === "OBSERVED_CORRELATION" ? "5 5" : null,
                      }}
                      onClick={() => {}}
                    />
                  );
                }
                return null;
              })}
            </g>
          )}

          {/* Focus on selected hypothesis overlay */}
          {selectedNode && nodes.some(n => n.type === "hypothesis" && n.id === selectedNode) && (
            <div className="hypothesis-focus-overlay">
              <p>Focused on selected hypothesis</p>
              <p>Viewing upstream dependencies and downstream effects</p>
            </div>
          )}
        </Flow>
      </div>

      {/* Detail panel side */}
      <aside className="causal-graph-panel">
        {selectedNode && (
          <div className="panel detail-panel">
            <h3 className="panel-title">
              {nodes.find(n => n.id === selectedNode)?.data?.label || "Node detail"}
            </h3>
            <div className="panel-content">
              {selectedNode && nodes.find(n => n.id === selectedNode) ? (
                <div className="detail-grid">
                  <div className="detail-item">
                    <strong>ID:</strong> {selectedNode}
                  </div>
                  <div className="detail-item">
                    <strong>Type:</strong> {nodes.find(n => n.id === selectedNode)?.type || "—"}
                  </div>
                  <div className="detail-item">
                    <strong>Label:</strong> {nodes.find(n => n.id === selectedNode)?.data?.label || "—"}
                  </div>
                  <div className="detail-item">
                    <strong>Evidence:</strong> {nodes.find(n => n.id === selectedNode)?.data?.evidenceCount || "—"}
                  </div>
                  {nodes.find(n => n.id === selectedNode)?.data?.confidence !== undefined && (
                    <div className="detail-item">
                      <strong>Confidence:</strong> {nodes.find(n => n.id === selectedNode)?.data?.confidence?.toFixed(2) || "—"}
                    </div>
                  )}
                  {nodes.find(n => n.id === selectedNode)?.data?.timestamp && (
                    <div className="detail-item">
                      <strong>Timestamp:</strong> {nodes.find(n => n.id === selectedNode)?.data?.timestamp}
                    </div>
                  )}
                </div>
              ) : (
                <p>No node selected</p>
              )}
            </div>
          </div>
        )}

        {selectedEdge && (
          <div className="panel detail-panel">
            <h3 className="panel-title">Edge Detail</h3>
            <div className="panel-content">
              {edges.find(e => e.id === selectedEdge) ? (
                <div className="detail-grid">
                  <div className="detail-item">
                    <strong>Type:</strong> {edges.find(e => e.id === selectedEdge)?.type || "—"}
                  </div>
                  <div className="detail-item">
                    <strong>Source:</strong> {edges.find(e => e.id === selectedEdge)?.source || "—"}
                  </div>
                  <div className="detail-item">
                    <strong>Target:</strong> {edges.find(e => e.id === selectedEdge)?.target || "—"}
                  </div>
                  <div className="detail-item">
                    <strong>Evidence:</strong> {edges.find(e => e.id === selectedEdge)?.data?.evidenceCount || "—"}
                  </div>
                  {edges.find(e => e.id === selectedEdge)?.data?.confidence !== undefined && (
                    <div className="detail-item">
                      <strong>Confidence:</strong> {edges.find(e => e.id === selectedEdge)?.data?.confidence?.toFixed(2) || "—"}
                    </div>
                  )}
                  {edges.find(e => e.id === selectedEdge)?.data?.timestamp && (
                    <div className="detail-item">
                      <strong>Timestamp:</strong> {edges.find(e => e.id === selectedEdge)?.data?.timestamp}
                    </div>
                  )}
                </div>
              ) : (
                <p>No edge selected</p>
              )}
            </div>
          </div>
        )}
      </aside>
    </div>
  );
}