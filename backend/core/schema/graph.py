from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Optional

import networkx as nx

from models.relationship import ConfidenceTier, InferredRelationship, ValidationStatus
from models.schema import SchemaSnapshot, TableProfile


@dataclass
class GraphNode:
    """A table node in the schema graph."""

    name: str
    row_count: Optional[int] = None
    primary_keys: list[str] = field(default_factory=list)
    column_count: int = 0
    analyst_note: Optional[str] = None


@dataclass
class GraphEdge:
    """A relationship edge between two table nodes."""

    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_id: str
    composite_score: float
    confidence: ConfidenceTier
    validation_status: ValidationStatus = ValidationStatus.PENDING
    relationship_type: str = "many-to-one"


class SchemaGraph:
    """
    In-memory directed graph of tables and their inferred relationships.

    Each node is a table. Each edge is an inferred (or confirmed) relationship
    between columns across tables.

    This graph is the live analytical surface during a session. It is rebuilt
    from the SchemaSnapshot + InferredRelationships stored in the memory DB.

    Design notes:
    - Directed: source.column → target.column (FK direction)
    - Multi-edge: two tables can have multiple relationships
    - Serializable: can be exported to JSON for frontend rendering
    """

    def __init__(self) -> None:
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()

    @classmethod
    def from_snapshot_and_relationships(
        cls,
        snapshot: SchemaSnapshot,
        relationships: list[InferredRelationship],
        decisions: dict[str, ValidationStatus] | None = None,
    ) -> "SchemaGraph":
        """
        Construct a SchemaGraph from a snapshot and its inferred relationships.

        Args:
            snapshot: The schema snapshot (provides table nodes).
            relationships: All inferred relationships (provides edges).
            decisions: Map of relationship_id → ValidationStatus (from memory DB).
        """
        graph = cls()
        decisions = decisions or {}

        for table in snapshot.tables:
            graph.add_table(table)

        for rel in relationships:
            status = decisions.get(rel.id, ValidationStatus.PENDING)
            graph.add_relationship(rel, validation_status=status)

        return graph

    def add_table(self, table: TableProfile) -> None:
        self._graph.add_node(
            table.name,
            row_count=table.row_count,
            primary_keys=table.primary_keys,
            column_count=len(table.columns),
            analyst_note=table.analyst_note,
        )

    def add_relationship(
        self,
        rel: InferredRelationship,
        validation_status: ValidationStatus = ValidationStatus.PENDING,
    ) -> None:
        # Ensure both table nodes exist even if not in snapshot (handles stale data)
        if rel.source_table not in self._graph:
            self._graph.add_node(rel.source_table)
        if rel.target_table not in self._graph:
            self._graph.add_node(rel.target_table)

        self._graph.add_edge(
            rel.source_table,
            rel.target_table,
            key=rel.id,
            source_column=rel.source_column,
            target_column=rel.target_column,
            relationship_id=rel.id,
            composite_score=rel.composite_score,
            confidence=rel.confidence.value,
            validation_status=validation_status.value,
            relationship_type=rel.relationship_type,
        )

    def get_neighbors(self, table_name: str) -> list[str]:
        """Tables directly connected to this table (in either direction)."""
        successors = list(self._graph.successors(table_name))
        predecessors = list(self._graph.predecessors(table_name))
        return list(set(successors + predecessors))

    def get_relationships_for_table(self, table_name: str) -> list[dict]:
        """All edges incident to a table."""
        edges = []
        for u, v, key, data in self._graph.edges(table_name, data=True, keys=True):
            edges.append({**data, "source_table": u, "target_table": v})
        for u, v, key, data in self._graph.in_edges(table_name, data=True, keys=True):
            if u != table_name:  # avoid duplicates
                edges.append({**data, "source_table": u, "target_table": v})
        return edges

    def find_join_path(self, source: str, target: str) -> Optional[list[str]]:
        """
        Find the shortest join path between two tables.
        Returns a list of table names forming the path, or None if no path exists.
        """
        try:
            # Use undirected view for path finding
            undirected = self._graph.to_undirected()
            path = nx.shortest_path(undirected, source, target)
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def get_isolated_tables(self) -> list[str]:
        """Tables with no inferred relationships — potential orphans."""
        return [n for n in self._graph.nodes if self._graph.degree(n) == 0]

    def get_hub_tables(self, top_n: int = 5) -> list[tuple[str, int]]:
        """Tables with the most relationships — likely fact/reference tables."""
        degrees = [(n, self._graph.degree(n)) for n in self._graph.nodes]
        return sorted(degrees, key=lambda x: x[1], reverse=True)[:top_n]

    @property
    def table_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def relationship_count(self) -> int:
        return self._graph.number_of_edges()

    def to_frontend_format(self) -> dict:
        """
        Serialize graph to React Flow-compatible nodes and edges format.
        Frontend uses this directly for rendering.
        """
        nodes = []
        for node_name, attrs in self._graph.nodes(data=True):
            nodes.append({
                "id": node_name,
                "type": "tableNode",
                "data": {
                    "label": node_name,
                    "rowCount": attrs.get("row_count"),
                    "columnCount": attrs.get("column_count", 0),
                    "primaryKeys": attrs.get("primary_keys", []),
                    "analystNote": attrs.get("analyst_note"),
                },
                "position": {"x": 0, "y": 0},  # Frontend positions these via layout
            })

        edges = []
        for u, v, key, data in self._graph.edges(data=True, keys=True):
            confidence = data.get("confidence", "speculative")
            edges.append({
                "id": key,
                "source": u,
                "target": v,
                "type": "relationshipEdge",
                "data": {
                    "sourceColumn": data.get("source_column"),
                    "targetColumn": data.get("target_column"),
                    "compositeScore": data.get("composite_score", 0),
                    "confidence": confidence,
                    "validationStatus": data.get("validation_status", "pending"),
                    "relationshipType": data.get("relationship_type", "many-to-one"),
                },
            })

        return {"nodes": nodes, "edges": edges}
