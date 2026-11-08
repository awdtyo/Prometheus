"""JSON and NetworkX views of the temporal causal graph.

``graph.json`` is the pipeline artifact; :class:`prometheus.contracts.GraphDocument`
is its validated representation. The NetworkX view is built on demand for
algorithms and is not a second source of truth.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from prometheus.contracts import GraphDocument

__all__ = [
    "read_graph",
    "to_networkx",
    "write_graph",
]


def write_graph(document: GraphDocument, path: str | Path) -> Path:
    """Write a graph document as deterministic JSON."""
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = document.model_dump(mode="json")
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def read_graph(path: str | Path) -> GraphDocument:
    """Read and validate a graph JSON artifact."""
    source = Path(path).expanduser()
    return GraphDocument.model_validate_json(source.read_text(encoding="utf-8"))


def to_networkx(document: GraphDocument) -> nx.DiGraph:
    """Build a ``networkx.DiGraph`` with observation and edge attributes."""
    graph = nx.DiGraph()
    for node in document.nodes:
        attributes = node.model_dump(mode="json")
        attributes["label"] = node.channel or f"event {node.id}"
        graph.add_node(node.id, **attributes)
    for edge in document.edges:
        graph.add_edge(edge.source, edge.target, **edge.model_dump(mode="json"))
    return graph
