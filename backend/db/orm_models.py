from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.session import Base


class ProjectORM(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    connection_config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    latest_snapshot_id: Mapped[str | None] = mapped_column(String)
    analyst_notes: Mapped[str | None] = mapped_column(Text)

    snapshots: Mapped[list["SchemaSnapshotORM"]] = relationship(
        "SchemaSnapshotORM", back_populates="project", cascade="all, delete-orphan"
    )
    relationships: Mapped[list["InferredRelationshipORM"]] = relationship(
        "InferredRelationshipORM", back_populates="project", cascade="all, delete-orphan"
    )
    decisions: Mapped[list["ValidationDecisionORM"]] = relationship(
        "ValidationDecisionORM", back_populates="project", cascade="all, delete-orphan"
    )
    annotations: Mapped[list["SemanticAnnotationORM"]] = relationship(
        "SemanticAnnotationORM", back_populates="project", cascade="all, delete-orphan"
    )
    dataset_plans: Mapped[list["DatasetPlanORM"]] = relationship(
        "DatasetPlanORM", back_populates="project", cascade="all, delete-orphan"
    )


class SchemaSnapshotORM(Base):
    __tablename__ = "schema_snapshots"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    connection_id: Mapped[str] = mapped_column(String, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    version: Mapped[int] = mapped_column(Integer, default=1)
    schema_data: Mapped[dict] = mapped_column(JSON, nullable=False)  # Full SchemaSnapshot

    project: Mapped["ProjectORM"] = relationship("ProjectORM", back_populates="snapshots")


class InferredRelationshipORM(Base):
    __tablename__ = "inferred_relationships"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        String, ForeignKey("schema_snapshots.id"), nullable=False
    )
    source_table: Mapped[str] = mapped_column(String, nullable=False)
    source_column: Mapped[str] = mapped_column(String, nullable=False)
    target_table: Mapped[str] = mapped_column(String, nullable=False)
    target_column: Mapped[str] = mapped_column(String, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(String(32), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(32), default="many-to-one")
    evidence_data: Mapped[list] = mapped_column(JSON, nullable=False)
    inferred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["ProjectORM"] = relationship(
        "ProjectORM", back_populates="relationships"
    )


class ValidationDecisionORM(Base):
    __tablename__ = "validation_decisions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    relationship_id: Mapped[str] = mapped_column(
        String, ForeignKey("inferred_relationships.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    analyst_notes: Mapped[str | None] = mapped_column(Text)
    corrected_source_column: Mapped[str | None] = mapped_column(String)
    corrected_target_table: Mapped[str | None] = mapped_column(String)
    corrected_target_column: Mapped[str | None] = mapped_column(String)

    project: Mapped["ProjectORM"] = relationship("ProjectORM", back_populates="decisions")


class SemanticAnnotationORM(Base):
    __tablename__ = "semantic_annotations"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_identifier: Mapped[str] = mapped_column(String(256), nullable=False)
    annotation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped["ProjectORM"] = relationship("ProjectORM", back_populates="annotations")


class DatasetPlanORM(Base):
    __tablename__ = "dataset_plans"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    plan_data: Mapped[dict] = mapped_column(JSON, nullable=False)  # Full DatasetPlan
    status: Mapped[str] = mapped_column(String(32), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped["ProjectORM"] = relationship("ProjectORM", back_populates="dataset_plans")
