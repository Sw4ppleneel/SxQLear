from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.errors import not_found
from core.memory.project_memory import ProjectMemoryService
from db.session import get_db
from models.memory import AnnotationTarget, AnnotationType, ProjectMemorySummary, SemanticAnnotation

router = APIRouter(prefix="/projects/{project_id}/memory", tags=["memory"])


class CreateAnnotationRequest(BaseModel):
    target_type: AnnotationTarget
    target_identifier: str
    annotation_type: AnnotationType
    text: str


@router.get("/summary", response_model=ProjectMemorySummary)
def get_memory_summary(
    project_id: str,
    db: Session = Depends(get_db),
) -> ProjectMemorySummary:
    """
    Return a high-level summary of what the system knows about this project.
    This is the 'orientation view' when returning to a project.
    """
    service = ProjectMemoryService(db)

    project = service.get_project(project_id)
    if not project:
        raise not_found("Project", project_id)

    return service.get_memory_summary(project_id)


@router.post("/annotations", response_model=SemanticAnnotation, status_code=201)
def add_annotation(
    project_id: str,
    req: CreateAnnotationRequest,
    db: Session = Depends(get_db),
) -> SemanticAnnotation:
    """
    Add a semantic annotation to a schema entity (table, column, or relationship).
    These annotations form the project's semantic layer.
    """
    service = ProjectMemoryService(db)

    project = service.get_project(project_id)
    if not project:
        raise not_found("Project", project_id)

    annotation = SemanticAnnotation(
        project_id=project_id,
        target_type=req.target_type,
        target_identifier=req.target_identifier,
        annotation_type=req.annotation_type,
        text=req.text,
    )
    service.add_annotation(annotation)
    return annotation


@router.get("/annotations", response_model=list[SemanticAnnotation])
def get_annotations(
    project_id: str,
    target_identifier: Optional[str] = None,
    db: Session = Depends(get_db),
) -> list[SemanticAnnotation]:
    """Return annotations, optionally filtered by target identifier."""
    service = ProjectMemoryService(db)
    return service.get_annotations(project_id, target_identifier)
