"""Temporal causal graph builder."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Sequence

import numpy as np

from autopsy.schemas.events import MissionEvent
from autopsy.schemas.graph import Graph, GraphEdge, GraphNode
from autopsy.schemas.observations import Observation
from autopsy.schemas.subsystems import SubsystemSpec
from autopsy.schemas.telemetry import TelemetryRecord
from autopsy.schemas.enums import NodeType, RelationshipType


@dataclass(frozen=True)
class GraphConfig:
    max_nodes: int = 150
    lag_tolerance_seconds: float = 30.0
    correlation_threshold: float = 0.3
    max_chain_len: int = 6


def _node_id_obs(obs: Observation) -> str:
    return f"obs:{obs.observation_id}"


def _node_id_event(ev: MissionEvent) -> str:
    return f"evt:{ev.event_id}"


def _allowed_lag(subsystem_a: str, subsystem_b: str, specs: dict[str, SubsystemSpec]) -> tuple[float, float] | None:
    spec_b = specs.get(subsystem_b)
    if spec_b is None:
        return None
    for dl in spec_b.dependency_lags:
        if dl.subsystem == subsystem_a:
            return (dl.min_lag_seconds, dl.max_lag_seconds)
    # fallback: if subsystem_a in dependencies but no lag, use default
    if subsystem_a in spec_b.dependencies:
        return (0.0, 300.0)
    return None


def _lagged_corr(series_a: list[float], series_b: list[float], lag: int) -> float:
    if lag < 0:
        return 0.0
    n = len(series_a)
    if n < 3 or len(series_b) < n:
        return 0.0
    # align: b[t] vs a[t-lag]
    xs = []
    ys = []
    for t in range(lag, n):
        xs.append(series_a[t - lag])
        ys.append(series_b[t])
    if len(xs) < 3:
        return 0.0
    xa = np.array(xs, dtype=float)
    ya = np.array(ys, dtype=float)
    if xa.std() == 0 or ya.std() == 0:
        return 0.0
    # pearson
    xa = (xa - xa.mean()) / xa.std()
    ya = (ya - ya.mean()) / ya.std()
    return float(np.mean(xa * ya))


def _null_corr(series_a: list[float], series_b: list[float], lag: int) -> float:
    # circular shift null
    if not series_a:
        return 0.0
    shifted = series_a[-lag:] + series_a[:-lag] if lag > 0 else series_a
    return _lagged_corr(shifted, series_b, lag)


def _build_series(
    telemetry: list[TelemetryRecord],
    subsystem: str,
    parameter: str | None = None,
) -> list[float]:
    vals = [r.value for r in telemetry if r.subsystem == subsystem and (parameter is None or r.parameter == parameter)]
    return vals


def build_graph(
    observations: list[Observation],
    events: list[MissionEvent],
    telemetry: list[TelemetryRecord],
    specs: dict[str, SubsystemSpec] | list[SubsystemSpec],
    config: GraphConfig | None = None,
    spec_aware: bool = True,
) -> Graph:
    cfg = config or GraphConfig()

    if isinstance(specs, list):
        spec_map = {s.id: s for s in specs}
    else:
        spec_map = specs

    # Build nodes
    nodes: list[GraphNode] = []
    obs_nodes: dict[str, Observation] = {}
    evt_nodes: dict[str, MissionEvent] = {}

    for obs in observations:
        nid = _node_id_obs(obs)
        nodes.append(GraphNode(
            node_id=nid,
            node_type=NodeType.OBSERVATION,
            label=f"{obs.subsystem}:{obs.observation_type}",
            timestamp=obs.timestamp,
            metadata={"subsystem": obs.subsystem, "severity": obs.severity.value, "source_ids": obs.source_ids},
        ))
        obs_nodes[nid] = obs

    for ev in events:
        nid = _node_id_event(ev)
        nodes.append(GraphNode(
            node_id=nid,
            node_type=NodeType.EVENT,
            label=f"{ev.subsystem}:{ev.event_type}",
            timestamp=ev.timestamp,
            metadata={"subsystem": ev.subsystem, "severity": ev.severity.value},
        ))
        evt_nodes[nid] = ev

    # Cap nodes
    if len(nodes) > cfg.max_nodes:
        # reduction rule: keep highest severity events/obs, drop lowest
        # sort by severity rank then timestamp
        sev_rank = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
        def rank(n: GraphNode) -> tuple[int, str]:
            sev = n.metadata.get("severity", "info")
            return (sev_rank.get(str(sev), 0), n.timestamp.isoformat() if n.timestamp else "")
        nodes.sort(key=rank, reverse=True)
        keep = set(n.node_id for n in nodes[:cfg.max_nodes])
        nodes = [n for n in nodes if n.node_id in keep]
        obs_nodes = {k: v for k, v in obs_nodes.items() if k in keep}
        evt_nodes = {k: v for k, v in evt_nodes.items() if k in keep}

    # Candidate edges
    edges: list[GraphEdge] = []
    edge_counter = 0

    node_list = list(obs_nodes.keys()) + list(evt_nodes.keys())
    # obs+event combined
    all_nodes = {**obs_nodes, **evt_nodes}

    for src_id, src_obj in all_nodes.items():
        for tgt_id, tgt_obj in all_nodes.items():
            if src_id == tgt_id:
                continue
            # determine subsystems
            if src_id.startswith("obs:"):
                src_sub = obs_nodes[src_id].subsystem
                src_ts = obs_nodes[src_id].timestamp
            else:
                src_sub = evt_nodes[src_id].subsystem
                src_ts = evt_nodes[src_id].timestamp
            if tgt_id.startswith("obs:"):
                tgt_sub = obs_nodes[tgt_id].subsystem
                tgt_ts = obs_nodes[tgt_id].timestamp
            else:
                tgt_sub = evt_nodes[tgt_id].subsystem
                tgt_ts = evt_nodes[tgt_id].timestamp

            if tgt_ts <= src_ts:
                continue  # no backward edges

            lag = (tgt_ts - src_ts).total_seconds()
            allowed = _allowed_lag(src_sub, tgt_sub, spec_map) if spec_aware else None

            # spec allows?
            spec_allowed = allowed is not None if spec_aware else True
            in_window = False
            if allowed is not None:
                mn, mx = allowed
                in_window = (mn - cfg.lag_tolerance_seconds) <= lag <= (mx + cfg.lag_tolerance_seconds)

            # correlation (only if same parameter available in telemetry)
            # use subsystem-level series
            src_series = _build_series(telemetry, src_sub)
            tgt_series = _build_series(telemetry, tgt_sub)
            corr = 0.0
            if len(src_series) > 0 and len(tgt_series) > 0 and len(src_series) == len(tgt_series):
                # use lag in samples
                sample_lag = max(1, int(lag / 60)) if lag > 0 else 1
                sample_lag = min(sample_lag, len(src_series) - 1)
                corr = _lagged_corr(src_series, tgt_series, sample_lag)
                null = _null_corr(src_series, tgt_series, sample_lag)
                corr = corr - null  # excess over null

            # magnitude factor
            if src_id.startswith("obs:"):
                mag = min(1.0, abs(obs_nodes[src_id].observed_value) / 100.0 + 0.5) if obs_nodes[src_id].observed_value else 0.5
            else:
                mag = 0.5

            # confidence
            if spec_allowed and in_window:
                conf = 0.3 + 0.4 * max(0.0, corr) + 0.2 * mag + 0.1 * (1.0 - min(1.0, lag / max(1.0, (allowed[1] if allowed else 300))))
                conf = min(1.0, max(0.0, conf))
                rtype = RelationshipType.TEMPORAL_PRECEDENCE
            elif spec_allowed:
                conf = 0.2 + 0.2 * max(0.0, corr)
                conf = min(1.0, max(0.0, conf))
                rtype = RelationshipType.TEMPORAL_PRECEDENCE
            else:
                # spec-forbidden: keep as correlated_not_causal (OBSERVED_CORRELATION) if corr high
                if abs(corr) >= cfg.correlation_threshold:
                    conf = 0.1 + 0.2 * abs(corr)
                    conf = min(0.4, max(0.0, conf))
                    rtype = RelationshipType.OBSERVED_CORRELATION
                else:
                    continue

            # prune: skip if confidence too low
            if conf < 0.15:
                continue

            edge_counter += 1
            eid = f"edg_{edge_counter:04d}"
            meta = {
                "lag_seconds": lag,
                "correlation": round(corr, 4),
                "spec_allowed": spec_allowed,
                "in_window": in_window,
                "rule": "spec_dependency" if spec_allowed else "correlated_not_causal",
            }
            if allowed is not None:
                meta["lag_window"] = [allowed[0], allowed[1]]

            edges.append(GraphEdge(
                edge_id=eid,
                source=src_id,
                target=tgt_id,
                relationship_type=rtype,
                evidence_ids=[],
                confidence=round(conf, 4),
                metadata=meta,
            ))

    # Prune dominated edges: if A->C and A->B->C with higher combined score, drop A->C
    # Simple: for each target, if there's an indirect path with higher score, drop direct
    # We'll do a simple dominance check
    edges = _prune(edges, all_nodes)

    return Graph(nodes=nodes, edges=edges)


def _prune(edges: list[GraphEdge], nodes: dict) -> list[GraphEdge]:
    # Build adjacency
    # For each edge (a,c), check if there exists b such that a->b and b->c with conf_a_b * conf_b_c > conf_a_c
    edge_map = {(e.source, e.target): e for e in edges}
    to_remove = set()
    for e in edges:
        a, c = e.source, e.target
        # find intermediate b
        for b in {x.source for x in edges if x.target == c} | {x.target for x in edges if x.source == a}:
            if b == a or b == c:
                continue
            e_ab = edge_map.get((a, b))
            e_bc = edge_map.get((b, c))
            if e_ab and e_bc:
                if e_ab.confidence * e_bc.confidence > e.confidence:
                    to_remove.add(e.edge_id)
    return [e for e in edges if e.edge_id not in to_remove]


# Helpers

def ancestors(graph: Graph, node_id: str) -> set[str]:
    adj = {e.target: e.source for e in graph.edges}
    result = set()
    cur = node_id
    while cur in adj:
        parent = adj[cur]
        if parent in result:
            break
        result.add(parent)
        cur = parent
    return result


def candidate_chains(graph: Graph, to_node: str, max_len: int = 6) -> list[list[str]]:
    # DFS from to_node backwards
    chains: list[list[str]] = []
    # build reverse adjacency
    rev: dict[str, list[str]] = {}
    for e in graph.edges:
        rev.setdefault(e.target, []).append(e.source)

    def dfs(node: str, path: list[str], visited: set[str]):
        if len(path) >= max_len:
            chains.append(list(path))
            return
        parents = rev.get(node, [])
        if not parents:
            chains.append(list(path))
            return
        for p in parents:
            if p in visited:
                continue
            visited.add(p)
            path.insert(0, p)
            dfs(p, path, visited)
            path.pop(0)
            visited.discard(p)

    dfs(to_node, [to_node], {to_node})
    if not chains:
        chains = [[to_node]]
    return chains


def subgraph_for_chain(graph: Graph, chain: list[str]) -> Graph:
    node_set = set(chain)
    nodes = [n for n in graph.nodes if n.node_id in node_set]
    edges = [e for e in graph.edges if e.source in node_set and e.target in node_set]
    return Graph(nodes=nodes, edges=edges)


def chain_score(graph: Graph, chain: list[str]) -> float:
    if len(chain) < 2:
        return 0.0
    edge_map = {(e.source, e.target): e.confidence for e in graph.edges}
    scores = []
    for i in range(len(chain) - 1):
        c = edge_map.get((chain[i], chain[i + 1]), 0.0)
        scores.append(c)
    if not scores:
        return 0.0
    return float(sum(scores) / len(scores))
