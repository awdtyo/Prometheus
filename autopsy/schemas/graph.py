"""Serializable causal/temporal graph contracts."""

from __future__ import annotations

from typing import Self

from pydantic import Field, field_validator, model_validator

from autopsy.schemas.base import (
    AutopsyModel,
    EntityId,
    JsonObject,
    Label,
    UtcDatetime,
    ensure_unique,
)
from autopsy.schemas.enums import NodeType, RelationshipType


class GraphNode(AutopsyModel):
    """One entity in the investigation graph."""

    node_id: EntityId = Field(description="Stable unique node identifier.")
    node_type: NodeType = Field(description="Kind of entity represented by the node.")
    label: Label = Field(description="Short human-readable label.")
    timestamp: UtcDatetime | None = Field(
        description="UTC instant associated with the node, or null for static nodes.",
    )
    metadata: JsonObject = Field(
        default_factory=dict,
        description="Additional JSON-serializable node attributes.",
    )


class GraphEdge(AutopsyModel):
    """One directed relationship between two graph nodes."""

    edge_id: EntityId = Field(description="Stable unique edge identifier.")
    source: EntityId = Field(description="Source node identifier.")
    target: EntityId = Field(description="Target node identifier.")
    relationship_type: RelationshipType = Field(description="Semantics of the relationship.")
    evidence_ids: list[EntityId] = Field(
        default_factory=list,
        description="Evidence records that justify the edge.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in the edge, from 0.0 to 1.0.",
    )
    metadata: JsonObject = Field(
        default_factory=dict,
        description="Additional JSON-serializable edge attributes.",
    )

    @field_validator("evidence_ids")
    @classmethod
    def _evidence_ids_are_unique(cls, value: list[str]) -> list[str]:
        ensure_unique(value, "evidence_ids")
        return value

    @model_validator(mode="after")
    def _reject_self_loop(self) -> Self:
        if self.source == self.target:
            raise ValueError("a graph edge cannot connect a node to itself")
        return self


class Graph(AutopsyModel):
    """An immutable-by-convention snapshot of an investigation graph.

    Referential integrity is validated on construction: every edge endpoint must
    name a node in the same snapshot, and node and edge identifiers must be
    unique.
    """

    nodes: list[GraphNode] = Field(
        default_factory=list,
        description="Nodes in the graph snapshot.",
    )
    edges: list[GraphEdge] = Field(
        default_factory=list,
        description="Directed edges in the graph snapshot.",
    )

    @model_validator(mode="after")
    def _validate_integrity(self) -> Self:
        node_ids = [node.node_id for node in self.nodes]
        ensure_unique(node_ids, "nodes.node_id")
        edge_ids = [edge.edge_id for edge in self.edges]
        ensure_unique(edge_ids, "edges.edge_id")

        known_nodes = set(node_ids)
        missing = sorted(
            {edge.source for edge in self.edges if edge.source not in known_nodes}
            | {edge.target for edge in self.edges if edge.target not in known_nodes}
        )
        if missing:
            raise ValueError(f"edges reference unknown node ids: {', '.join(missing)}")
        return self
