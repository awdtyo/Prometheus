"""Canonical node identifiers for the autopsy graph.

Graph nodes are addressed with a prefixed form (``obs:<observation_id>``,
``evt:<event_id>``) while raw observation/event records carry the opaque id
(``obs_adcs_attitude_error_deg_1``). Every layer that matches hypothesis
causal-chain ids, evidence citations or graph node ids must use these helpers
so a single canonical format is used everywhere (graph, agents, judge,
evaluation).
"""

from __future__ import annotations


def obs_node_id(observation_id: str) -> str:
    """Graph node id for an observation."""
    return f"obs:{observation_id}"


def evt_node_id(event_id: str) -> str:
    """Graph node id for a mission event."""
    return f"evt:{event_id}"


def parse_node_id(node_id: str) -> tuple[str, str]:
    """Split a prefixed node id into ``(kind, opaque_id)``.

    ``kind`` is ``"obs"`` or ``"evt"``.
    """
    kind, sep, rest = node_id.partition(":")
    if not sep:
        raise ValueError(f"not a prefixed node id: {node_id!r}")
    return kind, rest


def is_node_id(value: str) -> bool:
    return value.startswith("obs:") or value.startswith("evt:")
