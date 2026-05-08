from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from db.orm_models import (
    DatasetPlanORM,
    InferredRelationshipORM,
    ProjectORM,
    SchemaSnapshotORM,
    SemanticAnnotationORM,
    ValidationDecisionORM,
)
from models.dataset import DatasetPlan
from models.memory import Project, SemanticAnnotation
from models.relationship import InferredRelationship, ValidationDecision
from models.schema import SchemaSnapshot


class ProjectRepository:
    """CRUD operations for projects and their associated analytical memory."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Projects ──────────────────────────────────────────────────────────────

    def create_project(self, project: Project, connection_config_json: dict) -> ProjectORM:
        orm = ProjectORM(
            id=project.id,
            name=project.name,
            description=project.description,
            connection_config_json=connection_config_json,
            status=project.status,
            created_at=project.created_at,
            updated_at=project.updated_at,
        )
        self.db.add(orm)
        self.db.commit()
        self.db.refresh(orm)
        return orm

    def get_project(self, project_id: str) -> ProjectORM | None:
        return self.db.query(ProjectORM).filter(ProjectORM.id == project_id).first()

    def list_projects(self) -> list[ProjectORM]:
        return (
            self.db.query(ProjectORM)
            .filter(ProjectORM.status != "deleted")
            .order_by(ProjectORM.updated_at.desc())
            .all()
        )

    def update_project(self, project_id: str, **kwargs) -> ProjectORM | None:
        orm = self.get_project(project_id)
        if not orm:
            return None
        for key, value in kwargs.items():
            setattr(orm, key, value)
            # SQLAlchemy plain JSON columns don't always detect replacement as dirty
            # in SQLite. flag_modified forces the column into the UPDATE statement.
            if isinstance(value, dict):
                flag_modified(orm, key)
        orm.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(orm)
        return orm

    def delete_project(self, project_id: str) -> bool:
        orm = self.get_project(project_id)
        if not orm:
            return False
        orm.status = "deleted"
        self.db.commit()
        return True

    # ── Schema Snapshots ──────────────────────────────────────────────────────

    def save_snapshot(self, snapshot: SchemaSnapshot) -> SchemaSnapshotORM:
        orm = SchemaSnapshotORM(
            id=snapshot.id,
            project_id=snapshot.project_id,
            connection_id=snapshot.connection_id,
            captured_at=snapshot.captured_at,
            version=snapshot.version,
            schema_data=snapshot.model_dump(mode="json"),
        )
        self.db.add(orm)
        self.db.commit()
        self.db.refresh(orm)
        # Update project's latest snapshot reference
        self.update_project(snapshot.project_id, latest_snapshot_id=snapshot.id)
        return orm

    def get_snapshot(self, snapshot_id: str) -> SchemaSnapshot | None:
        orm = (
            self.db.query(SchemaSnapshotORM)
            .filter(SchemaSnapshotORM.id == snapshot_id)
            .first()
        )
        if not orm:
            return None
        return SchemaSnapshot.model_validate(orm.schema_data)

    def get_latest_snapshot(self, project_id: str) -> SchemaSnapshot | None:
        project = self.get_project(project_id)
        if not project or not project.latest_snapshot_id:
            return None
        return self.get_snapshot(project.latest_snapshot_id)

    # ── Inferred Relationships ────────────────────────────────────────────────

    def save_relationships(
        self, project_id: str, snapshot_id: str, relationships: list[InferredRelationship]
    ) -> int:
        """Bulk-save inferred relationships. Returns count saved."""
        for rel in relationships:
            orm = InferredRelationshipORM(
                id=rel.id,
                project_id=project_id,
                snapshot_id=snapshot_id,
                source_table=rel.source_table,
                source_column=rel.source_column,
                target_table=rel.target_table,
                target_column=rel.target_column,
                composite_score=rel.composite_score,
                confidence=rel.confidence.value,
                relationship_type=rel.relationship_type,
                evidence_data=[e.model_dump(mode="json") for e in rel.evidence],
                inferred_at=rel.inferred_at,
            )
            self.db.merge(orm)  # upsert by ID
        self.db.commit()
        return len(relationships)

    def get_relationships(
        self, project_id: str, snapshot_id: str | None = None
    ) -> list[InferredRelationship]:
        query = self.db.query(InferredRelationshipORM).filter(
            InferredRelationshipORM.project_id == project_id
        )
        if snapshot_id:
            query = query.filter(InferredRelationshipORM.snapshot_id == snapshot_id)
        orms = query.order_by(InferredRelationshipORM.composite_score.desc()).all()
        return [
            InferredRelationship(
                id=o.id,
                source_table=o.source_table,
                source_column=o.source_column,
                target_table=o.target_table,
                target_column=o.target_column,
                composite_score=o.composite_score,
                confidence=o.confidence,
                relationship_type=o.relationship_type,
                evidence=o.evidence_data,
                snapshot_id=o.snapshot_id,
                inferred_at=o.inferred_at,
            )
            for o in orms
        ]

    # ── Validation Decisions ──────────────────────────────────────────────────

    def save_decision(self, decision: ValidationDecision) -> ValidationDecisionORM:
        orm = ValidationDecisionORM(
            id=decision.id,
            project_id=decision.project_id,
            relationship_id=decision.relationship_id,
            status=decision.status.value,
            decided_at=decision.decided_at,
            analyst_notes=decision.analyst_notes,
            corrected_source_column=decision.corrected_source_column,
            corrected_target_table=decision.corrected_target_table,
            corrected_target_column=decision.corrected_target_column,
        )
        self.db.merge(orm)
        self.db.commit()
        return orm

    def get_decisions(self, project_id: str) -> list[ValidationDecisionORM]:
        return (
            self.db.query(ValidationDecisionORM)
            .filter(ValidationDecisionORM.project_id == project_id)
            .order_by(ValidationDecisionORM.decided_at.desc())
            .all()
        )

    def get_decision_for_relationship(
        self, project_id: str, relationship_id: str
    ) -> ValidationDecisionORM | None:
        return (
            self.db.query(ValidationDecisionORM)
            .filter(
                ValidationDecisionORM.project_id == project_id,
                ValidationDecisionORM.relationship_id == relationship_id,
            )
            .order_by(ValidationDecisionORM.decided_at.desc())
            .first()
        )

    # ── Semantic Annotations ──────────────────────────────────────────────────

    def save_annotation(self, annotation: SemanticAnnotation) -> SemanticAnnotationORM:
        orm = SemanticAnnotationORM(
            id=annotation.id,
            project_id=annotation.project_id,
            target_type=annotation.target_type.value,
            target_identifier=annotation.target_identifier,
            annotation_type=annotation.annotation_type.value,
            text=annotation.text,
            created_at=annotation.created_at,
            updated_at=annotation.updated_at,
        )
        self.db.merge(orm)
        self.db.commit()
        return orm

    def get_annotations(
        self, project_id: str, target_identifier: str | None = None
    ) -> list[SemanticAnnotationORM]:
        query = self.db.query(SemanticAnnotationORM).filter(
            SemanticAnnotationORM.project_id == project_id
        )
        if target_identifier:
            query = query.filter(
                SemanticAnnotationORM.target_identifier == target_identifier
            )
        return query.order_by(SemanticAnnotationORM.created_at.desc()).all()

    # ── Dataset Plans ─────────────────────────────────────────────────────────

    def save_dataset_plan(self, plan: DatasetPlan) -> DatasetPlanORM:
        orm = DatasetPlanORM(
            id=plan.id,
            project_id=plan.project_id,
            name=plan.name,
            description=plan.description,
            plan_data=plan.model_dump(mode="json"),
            status=plan.status.value,
            created_at=plan.created_at,
            updated_at=plan.updated_at,
            is_verified=plan.status.value == "verified",
        )
        self.db.merge(orm)
        self.db.commit()
        return orm

    def get_dataset_plans(self, project_id: str) -> list[DatasetPlanORM]:
        return (
            self.db.query(DatasetPlanORM)
            .filter(DatasetPlanORM.project_id == project_id)
            .order_by(DatasetPlanORM.updated_at.desc())
            .all()
        )

    def get_dataset_plan(self, plan_id: str) -> DatasetPlan | None:
        orm = self.db.query(DatasetPlanORM).filter(DatasetPlanORM.id == plan_id).first()
        if not orm:
            return None
        return DatasetPlan.model_validate(orm.plan_data)
