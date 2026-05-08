from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class JoinType(str, Enum):
    INNER = "INNER"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    FULL = "FULL"


class JoinClause(BaseModel):
    """
    A single join step in a dataset construction plan.
    Every join must be traceable to either a confirmed relationship or explicit analyst reasoning.
    """

    join_type: JoinType = JoinType.LEFT
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    relationship_id: Optional[str] = None  # Links to confirmed InferredRelationship
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str  # Why this join was included — always required


class ColumnSelection(BaseModel):
    """A column selected for inclusion in the output dataset."""

    table: str
    column: str
    alias: Optional[str] = None
    transformation: Optional[str] = None  # e.g., "CAST(x AS DATE)"
    notes: Optional[str] = None


class FilterCondition(BaseModel):
    """A filter applied to the dataset."""

    table: str
    column: str
    operator: str  # "=", "!=", ">", "IS NULL", "IN", etc.
    value: Any
    reasoning: Optional[str] = None


class DatasetPlanStatus(str, Enum):
    DRAFT = "draft"
    VERIFIED = "verified"
    DEPRECATED = "deprecated"


class DatasetPlan(BaseModel):
    """
    A provenance-aware, annotated dataset construction plan.

    This is the primary output of SxQLear. It is NOT just a SQL query —
    it is a reasoned, documented plan that explains every join, assumption,
    and transformation, so analysts can trust what they're building.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    name: str = Field(..., min_length=1, max_length=128)
    description: str
    base_table: str

    joins: list[JoinClause] = Field(default_factory=list)
    selected_columns: list[ColumnSelection] = Field(default_factory=list)
    filters: list[FilterCondition] = Field(default_factory=list)

    # Trust & provenance metadata
    assumptions: list[str] = Field(
        default_factory=list,
        description="Explicit assumptions the analyst is making about this dataset",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Known data quality issues or risks the analyst should verify",
    )
    grain_description: Optional[str] = Field(
        default=None,
        description="What does one row represent? Critical for preventing aggregation errors.",
    )

    status: DatasetPlanStatus = DatasetPlanStatus.DRAFT
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Generated SQL — populated by the SQL generator after plan is reviewed
    generated_sql: Optional[str] = None
    sql_generated_at: Optional[datetime] = None

    @property
    def is_safe_to_use(self) -> bool:
        """
        Heuristic check: plan has grain description and no unresolved warnings.
        This is informational, not a hard gate.
        """
        return self.grain_description is not None and self.status == DatasetPlanStatus.VERIFIED
