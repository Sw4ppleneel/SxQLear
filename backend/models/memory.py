from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AnnotationTarget(str, Enum):
    TABLE = "table"
    COLUMN = "column"
    RELATIONSHIP = "relationship"


class AnnotationType(str, Enum):
    DESCRIPTION = "description"    # What this entity represents
    WARNING = "warning"            # Known issue or data quality concern
    CONTEXT = "context"            # Business/domain context
    ASSUMPTION = "assumption"      # Analytical assumption being made
    GRAIN = "grain"                # What one row represents (critical for aggs)


class SemanticAnnotation(BaseModel):
    """
    An analyst's annotation on a schema entity.
    These form the semantic layer of the project memory.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    target_type: AnnotationTarget
    target_identifier: str = Field(
        description="Dot-notation identifier, e.g. 'orders', 'orders.customer_id', or relationship ID"
    )
    annotation_type: AnnotationType
    text: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class Project(BaseModel):
    """
    A SxQLear project — the scope for all analytical memory.
    One project = one target database being analyzed.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    connection_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="active")

    # IDs of the latest schema snapshot and validation state
    latest_snapshot_id: Optional[str] = None
    validated_relationship_count: int = 0
    confirmed_relationship_count: int = 0


class ProjectMemorySummary(BaseModel):
    """
    High-level summary of what is known about a project.
    Returned on project load to give the analyst immediate context.
    """

    project_id: str
    table_count: int
    total_inferred_relationships: int
    confirmed_relationships: int
    rejected_relationships: int
    pending_relationships: int
    annotation_count: int
    last_crawl_at: Optional[datetime] = None
    last_validation_at: Optional[datetime] = None
    analyst_notes: Optional[str] = None
