"""Orchestrate temporal causal graph construction for one mission.

The stage reads only the mission directory and the Phase 3 observation set. It
writes ``graph.json`` and a self-contained ``graph.html`` next to the telemetry.
Ground truth is never opened.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from prometheus.contracts import GraphDocument, ObservationSet
from prometheus.graph.build import GraphConfig, build_graph
from prometheus.graph.io import write_graph
from prometheus.graph.render import render_html
from prometheus.ingest import IngestedRun, ingest_run
from prometheus.observations import extract_observations

__all__ = [
    "GraphResult",
    "build_graph_run",
]

_DEFAULT_JSON = "graph.json"
_DEFAULT_HTML = "graph.html"


@dataclass(frozen=True)
class GraphResult:
    """A mission, its observations, the graph and the written artifacts."""

    ingested: IngestedRun
    observations: ObservationSet
    document: GraphDocument
    json_path: Path
    html_path: Path

    @property
    def spec_edges(self) -> int:
        """Number of spec-supported edges."""
        return sum(edge.spec_support for edge in self.document.edges)

    @property
    def data_edges(self) -> int:
        """Number of data-only edges."""
        return len(self.document.edges) - self.spec_edges


def build_graph_run(
    run_dir: str | Path,
    *,
    observations: ObservationSet | None = None,
    config: GraphConfig | None = None,
    json_path: str | Path | None = None,
    html_path: str | Path | None = None,
) -> GraphResult:
    """Ingest, observe if needed, build, write and return the graph."""
    ingested = ingest_run(run_dir)
    observation_set = observations or extract_observations(ingested)
    document = build_graph(ingested, observation_set, config)
    config = config or GraphConfig()

    target_json = (
        Path(json_path).expanduser()
        if json_path is not None
        else ingested.run_dir / _DEFAULT_JSON
    )
    target_html = (
        Path(html_path).expanduser()
        if html_path is not None
        else ingested.run_dir / _DEFAULT_HTML
    )
    write_graph(document, target_json)
    render_html(document, target_html, grid_s=config.grid_s)
    return GraphResult(
        ingested=ingested,
        observations=observation_set,
        document=document,
        json_path=target_json,
        html_path=target_html,
    )
