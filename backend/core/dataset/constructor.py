from __future__ import annotations

import logging
from typing import Optional

from models.dataset import (
    ColumnSelection,
    DatasetPlan,
    FilterCondition,
    JoinClause,
    JoinType,
)
from models.memory import SemanticAnnotation
from models.relationship import InferredRelationship, ValidationStatus
from models.schema import SchemaSnapshot

logger = logging.getLogger(__name__)


class DatasetConstructor:
    """
    Constructs DatasetPlan objects from confirmed relationships and analyst intent.

    The end goal is NOT SQL generation. The end goal is a trustworthy,
    provenance-aware, annotated plan that an analyst can inspect, verify,
    and trust before using the data.

    Design principles:
    ─────────────────────────────────────────────────────────────────────────────
    - Every join in the plan links back to a confirmed relationship ID.
    - Assumptions and warnings are explicit, not buried.
    - Grain description is surfaced prominently — it prevents aggregation errors.
    - The plan is the primary artifact; SQL is a derived output.
    """

    def build_plan(
        self,
        project_id: str,
        name: str,
        description: str,
        base_table: str,
        snapshot: SchemaSnapshot,
        confirmed_relationships: list[InferredRelationship],
        selected_tables: list[str],
        filters: Optional[list[FilterCondition]] = None,
        grain_description: Optional[str] = None,
    ) -> DatasetPlan:
        """
        Build a DatasetPlan from a base table and a set of tables to join.

        Args:
            project_id: The project this plan belongs to.
            name: Human-readable name for the plan.
            description: What this dataset is for.
            base_table: The anchor table (FROM clause).
            snapshot: Current schema snapshot for column metadata.
            confirmed_relationships: Only confirmed relationships are used in plans.
            selected_tables: Tables to include in the plan (joined from base_table).
            filters: Optional filter conditions.
            grain_description: What does one row represent? (critical)
        """
        joins = self._build_joins(
            base_table, selected_tables, confirmed_relationships, snapshot
        )

        selected_columns = self._build_column_selections(
            [base_table] + selected_tables, snapshot
        )

        assumptions, warnings = self._derive_assumptions_and_warnings(
            base_table, joins, snapshot, confirmed_relationships
        )

        if grain_description is None:
            warnings.append(
                "Grain description not specified. Define what one row represents "
                "before using this dataset for aggregations or metrics."
            )

        plan = DatasetPlan(
            project_id=project_id,
            name=name,
            description=description,
            base_table=base_table,
            joins=joins,
            selected_columns=selected_columns,
            filters=filters or [],
            assumptions=assumptions,
            warnings=warnings,
            grain_description=grain_description,
        )

        logger.info(
            "Built dataset plan '%s': %d joins, %d columns, %d warnings",
            name, len(joins), len(selected_columns), len(warnings),
        )
        return plan

    def _build_joins(
        self,
        base_table: str,
        target_tables: list[str],
        confirmed_relationships: list[InferredRelationship],
        snapshot: SchemaSnapshot,
    ) -> list[JoinClause]:
        """
        Determine the join path from base_table to each target_table.
        Only uses confirmed relationships — never inferred-only relationships.
        """
        # Build a lookup of confirmed relationships by (source, target) pair
        rel_map: dict[tuple[str, str], InferredRelationship] = {}
        for rel in confirmed_relationships:
            rel_map[(rel.source_table, rel.target_table)] = rel
            # Also index the reverse direction for flexibility
            rel_map[(rel.target_table, rel.source_table)] = rel

        joins: list[JoinClause] = []
        all_tables = set([base_table] + [j.right_table for j in joins])

        for target in target_tables:
            if target == base_table:
                continue

            # Find a direct relationship
            rel = rel_map.get((base_table, target)) or rel_map.get((target, base_table))

            if rel is None:
                # Try to find a path through already-joined tables
                for joined_table in list(all_tables):
                    rel = rel_map.get((joined_table, target)) or rel_map.get((target, joined_table))
                    if rel:
                        break

            if rel is None:
                logger.warning(
                    "No confirmed relationship found between '%s' and '%s' — "
                    "table will be excluded from plan",
                    base_table, target,
                )
                continue

            # Determine join direction
            if rel.source_table == target:
                left_table = target
                left_col = rel.source_column
                right_table = rel.target_table
                right_col = rel.target_column
            else:
                left_table = rel.source_table
                left_col = rel.source_column
                right_table = rel.target_table
                right_col = rel.target_column

            joins.append(JoinClause(
                join_type=JoinType.LEFT,
                left_table=left_table,
                left_column=left_col,
                right_table=right_table,
                right_column=right_col,
                relationship_id=rel.id,
                confidence=rel.composite_score,
                reasoning=(
                    f"Confirmed join: {left_table}.{left_col} → {right_table}.{right_col} "
                    f"(confidence: {rel.composite_score:.0%})"
                ),
            ))
            all_tables.add(target)

        return joins

    @staticmethod
    def _build_column_selections(
        tables: list[str],
        snapshot: SchemaSnapshot,
    ) -> list[ColumnSelection]:
        """Select all non-binary, non-JSON columns from the specified tables."""
        from models.schema import ColumnType
        skip_types = {ColumnType.BYTES, ColumnType.JSON}

        selections: list[ColumnSelection] = []
        for table_name in tables:
            table = snapshot.get_table(table_name)
            if not table:
                continue
            for col in table.columns:
                if col.normalized_type in skip_types:
                    continue
                selections.append(ColumnSelection(table=table_name, column=col.name))

        return selections

    @staticmethod
    def _derive_assumptions_and_warnings(
        base_table: str,
        joins: list[JoinClause],
        snapshot: SchemaSnapshot,
        confirmed_relationships: list[InferredRelationship],
    ) -> tuple[list[str], list[str]]:
        """Derive explicit assumptions and data quality warnings from the plan."""
        assumptions: list[str] = []
        warnings: list[str] = []

        # LEFT JOINs produce NULLs — note this
        left_joins = [j for j in joins if j.join_type == JoinType.LEFT]
        if left_joins:
            tables = ", ".join(f"'{j.right_table}'" for j in left_joins)
            assumptions.append(
                f"LEFT JOINs are used for {tables}. Rows with no match will have "
                f"NULL values for those table's columns. Count-based metrics may be affected."
            )

        # Check for fanout risk: joining multiple many-to-one tables off the same base
        many_to_one_joins = [j for j in joins]
        if len(many_to_one_joins) > 1:
            warnings.append(
                "Multiple joins from the same base table. Verify that no join introduces "
                "row duplication (fanout). Check grain carefully before aggregating."
            )

        # Note base table row count if available
        base = snapshot.get_table(base_table)
        if base and base.row_count:
            assumptions.append(
                f"Base table '{base_table}' has approximately {base.row_count:,} rows "
                f"at time of schema crawl."
            )

        return assumptions, warnings
