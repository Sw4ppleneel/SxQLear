from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from db.repositories.project_repo import ProjectRepository
from models.memory import Project, ProjectMemorySummary, SemanticAnnotation
from models.relationship import InferredRelationship, ValidationDecision, ValidationStatus
from models.schema import SchemaSnapshot

logger = logging.getLogger(__name__)


class ProjectMemoryService:
    """
    The analytical memory service for a SxQLear project.

    This is NOT a simple CRUD wrapper. It is the stateful cognition layer
    that accumulates understanding over time. It answers questions like:
    - What has already been confirmed about this schema?
    - What was the reasoning behind a past decision?
    - What assumptions are we making in this dataset plan?

    All decisions are append-only in spirit — we never silently overwrite history.
    """

    def __init__(self, db: Session) -> None:
        self._repo = ProjectRepository(db)

    # ── Project lifecycle ─────────────────────────────────────────────────────

    def create_project(
        self,
        name: str,
        connection_config: dict,
        description: str | None = None,
    ) -> Project:
        """Create a new project. Connection config is stored as JSON (no secrets in plain text)."""
        project = Project(
            name=name,
            description=description,
            connection_id=connection_config.get("id", ""),
        )
        self._repo.create_project(project, connection_config_json=connection_config)
        logger.info("Created project %s (%s)", project.id, project.name)
        return project

    def get_project(self, project_id: str) -> Project | None:
        orm = self._repo.get_project(project_id)
        if not orm:
            return None
        return Project(
            id=orm.id,
            name=orm.name,
            description=orm.description,
            connection_id=orm.connection_config_json.get("id", ""),
            created_at=orm.created_at,
            updated_at=orm.updated_at,
            status=orm.status,
            latest_snapshot_id=orm.latest_snapshot_id,
        )

    def list_projects(self) -> list[Project]:
        orms = self._repo.list_projects()
        return [
            Project(
                id=o.id,
                name=o.name,
                description=o.description,
                connection_id=o.connection_config_json.get("id", ""),
                created_at=o.created_at,
                updated_at=o.updated_at,
                status=o.status,
                latest_snapshot_id=o.latest_snapshot_id,
            )
            for o in orms
        ]

    def get_connection_config(self, project_id: str) -> dict | None:
        """Retrieve the raw connection config JSON. Caller handles deserialization."""
        orm = self._repo.get_project(project_id)
        return orm.connection_config_json if orm else None

    # ── Schema snapshots ──────────────────────────────────────────────────────

    def save_snapshot(self, snapshot: SchemaSnapshot) -> None:
        self._repo.save_snapshot(snapshot)
        logger.info(
            "Saved snapshot %s for project %s (%d tables)",
            snapshot.id, snapshot.project_id, len(snapshot.tables),
        )

    def get_latest_snapshot(self, project_id: str) -> SchemaSnapshot | None:
        return self._repo.get_latest_snapshot(project_id)

    # ── Relationship inference results ────────────────────────────────────────

    def save_inferred_relationships(
        self,
        project_id: str,
        snapshot_id: str,
        relationships: list[InferredRelationship],
    ) -> None:
        count = self._repo.save_relationships(project_id, snapshot_id, relationships)
        logger.info("Saved %d inferred relationships for project %s", count, project_id)

    def get_inferred_relationships(
        self,
        project_id: str,
        snapshot_id: str | None = None,
    ) -> list[InferredRelationship]:
        return self._repo.get_relationships(project_id, snapshot_id)

    # ── Validation decisions ──────────────────────────────────────────────────

    def record_decision(self, decision: ValidationDecision) -> None:
        """
        Record an analyst's decision about an inferred relationship.
        This is the primary way the analytical memory grows.
        """
        self._repo.save_decision(decision)
        logger.info(
            "Decision recorded: relationship=%s status=%s",
            decision.relationship_id, decision.status.value,
        )

    def get_decisions(self, project_id: str) -> list[ValidationDecision]:
        orms = self._repo.get_decisions(project_id)
        return [
            ValidationDecision(
                id=o.id,
                project_id=o.project_id,
                relationship_id=o.relationship_id,
                status=ValidationStatus(o.status),
                decided_at=o.decided_at,
                analyst_notes=o.analyst_notes,
                corrected_source_column=o.corrected_source_column,
                corrected_target_table=o.corrected_target_table,
                corrected_target_column=o.corrected_target_column,
            )
            for o in orms
        ]

    def get_decision_map(self, project_id: str) -> dict[str, ValidationStatus]:
        """Returns {relationship_id: ValidationStatus} for quick lookup."""
        decisions = self.get_decisions(project_id)
        # Later decisions override earlier ones for the same relationship
        result: dict[str, ValidationStatus] = {}
        for d in reversed(decisions):  # reversed = oldest first, later ones overwrite
            result[d.relationship_id] = d.status
        return result

    def get_confirmed_relationship_ids(self, project_id: str) -> set[str]:
        decision_map = self.get_decision_map(project_id)
        return {rid for rid, status in decision_map.items() if status == ValidationStatus.CONFIRMED}

    # ── Semantic annotations ──────────────────────────────────────────────────

    def add_annotation(self, annotation: SemanticAnnotation) -> None:
        self._repo.save_annotation(annotation)

    def get_annotations(
        self, project_id: str, target_identifier: str | None = None
    ) -> list[SemanticAnnotation]:
        from models.memory import AnnotationTarget, AnnotationType
        orms = self._repo.get_annotations(project_id, target_identifier)
        return [
            SemanticAnnotation(
                id=o.id,
                project_id=o.project_id,
                target_type=AnnotationTarget(o.target_type),
                target_identifier=o.target_identifier,
                annotation_type=AnnotationType(o.annotation_type),
                text=o.text,
                created_at=o.created_at,
                updated_at=o.updated_at,
            )
            for o in orms
        ]

    # ── Project memory summary ────────────────────────────────────────────────

    def get_memory_summary(self, project_id: str) -> ProjectMemorySummary:
        """
        Build a high-level summary of what the system knows about this project.
        Returned on project load to give the analyst immediate orientation.
        """
        snapshot = self.get_latest_snapshot(project_id)
        relationships = self.get_inferred_relationships(project_id)
        decision_map = self.get_decision_map(project_id)
        annotations = self.get_annotations(project_id)

        confirmed = sum(1 for s in decision_map.values() if s == ValidationStatus.CONFIRMED)
        rejected = sum(1 for s in decision_map.values() if s == ValidationStatus.REJECTED)
        decided_ids = set(decision_map.keys())
        pending = sum(1 for r in relationships if r.id not in decided_ids)

        return ProjectMemorySummary(
            project_id=project_id,
            table_count=len(snapshot.tables) if snapshot else 0,
            total_inferred_relationships=len(relationships),
            confirmed_relationships=confirmed,
            rejected_relationships=rejected,
            pending_relationships=pending,
            annotation_count=len(annotations),
            last_crawl_at=snapshot.captured_at if snapshot else None,
        )
