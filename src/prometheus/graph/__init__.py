"""Temporal causal graph: observations as nodes, evidence-scored links as edges.

Public entry point: :func:`build_graph_run` for the CLI, and
:func:`prometheus.graph.build_graph` for in-process callers. The graph is a
NetworkX ``DiGraph`` view over the validated ``GraphDocument`` contract and is
serialized deterministically as ``graph.json``.
"""

from prometheus.graph.build import GraphConfig, build_graph
from prometheus.graph.evidence import (
    EdgeEvidence,
    ResidualSeries,
    channel_residual,
    measure_edge,
)
from prometheus.graph.io import read_graph, to_networkx, write_graph
from prometheus.graph.render import render_html
from prometheus.graph.run import GraphResult, build_graph_run

__all__ = [
    "EdgeEvidence",
    "GraphConfig",
    "GraphResult",
    "ResidualSeries",
    "build_graph",
    "build_graph_run",
    "channel_residual",
    "measure_edge",
    "read_graph",
    "render_html",
    "to_networkx",
    "write_graph",
]
