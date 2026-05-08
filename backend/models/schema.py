from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ColumnType(str, Enum):
    """Canonical column type taxonomy, independent of DB dialect."""

    INTEGER = "integer"
    BIGINT = "bigint"
    FLOAT = "float"
    DECIMAL = "decimal"
    VARCHAR = "varchar"
    TEXT = "text"
    BOOLEAN = "boolean"
    DATE = "date"
    TIMESTAMP = "timestamp"
    JSON = "json"
    UUID = "uuid"
    BYTES = "bytes"
    OTHER = "other"


class ColumnProfile(BaseModel):
    """
    Full profile of a single database column.

    Statistical fields (null_count, distinct_count, sample_values) are
    populated only when profiling is enabled and the user has consented.
    They are never mandatory; inference must work without them.
    """

    name: str
    raw_type: str  # Verbatim type string from the DB (e.g. "character varying(255)")
    normalized_type: ColumnType
    is_nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    referenced_table: Optional[str] = None
    referenced_column: Optional[str] = None
    has_index: bool = False
    ordinal_position: Optional[int] = None

    # Statistical profile — opt-in, populated by the crawler
    row_count: Optional[int] = None       # Total rows in the parent table
    null_count: Optional[int] = None      # Rows where this column is NULL
    distinct_count: Optional[int] = None  # Cardinality estimate
    sample_values: list[str] = Field(default_factory=list)  # Up to N non-null samples

    # Analyst annotations — set by the user via validation/annotation flows
    analyst_note: Optional[str] = None

    @property
    def null_rate(self) -> Optional[float]:
        if self.null_count is not None and self.row_count and self.row_count > 0:
            return self.null_count / self.row_count
        return None

    @property
    def selectivity(self) -> Optional[float]:
        """Ratio of distinct values to total rows. 1.0 = unique key."""
        if self.distinct_count is not None and self.row_count and self.row_count > 0:
            return self.distinct_count / self.row_count
        return None


class ForeignKeyConstraint(BaseModel):
    """An explicitly declared FK constraint from the database DDL."""

    constrained_columns: list[str]
    referred_schema: Optional[str] = None
    referred_table: str
    referred_columns: list[str]
    name: Optional[str] = None  # Constraint name if declared


class TableProfile(BaseModel):
    """
    Full profile of a single database table including all its columns,
    constraints, and statistical metadata.
    """

    name: str
    schema_name: Optional[str] = None
    row_count: Optional[int] = None
    columns: list[ColumnProfile] = Field(default_factory=list)
    primary_keys: list[str] = Field(default_factory=list)
    foreign_key_constraints: list[ForeignKeyConstraint] = Field(default_factory=list)
    index_names: list[str] = Field(default_factory=list)

    # Analyst annotations
    analyst_note: Optional[str] = None
    analyst_tags: list[str] = Field(default_factory=list)

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]

    def get_column(self, name: str) -> Optional[ColumnProfile]:
        for col in self.columns:
            if col.name == name:
                return col
        return None

    def get_pk_column(self) -> Optional[ColumnProfile]:
        """Return the first primary key column, or None."""
        if not self.primary_keys:
            return None
        return self.get_column(self.primary_keys[0])


class SchemaSnapshot(BaseModel):
    """
    A complete, versioned capture of a database schema at a point in time.
    This is the foundational input to the inference engine.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    connection_id: str
    project_id: str
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1
    tables: list[TableProfile] = Field(default_factory=list)
    notes: Optional[str] = None

    @property
    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    def get_table(self, name: str) -> Optional[TableProfile]:
        for t in self.tables:
            if t.name == name:
                return t
        return None

    @property
    def total_columns(self) -> int:
        return sum(len(t.columns) for t in self.tables)

    @property
    def explicit_fk_count(self) -> int:
        return sum(len(t.foreign_key_constraints) for t in self.tables)
