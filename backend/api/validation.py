from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.errors import not_found
from core.memory.project_memory import ProjectMemoryService
from core.validation.validator import ValidationQueue, build_validation_decision
from db.session import get_db
from models.relationship import ValidationDecision, ValidationStatus

router = APIRouter(prefix="/projects/{project_id}/validation", tags=["validation"])


class DecisionRequest(BaseModel):
    relationship_id: str
    status: ValidationStatus
    analyst_notes: Optional[str] = None
    correction: Optional[dict] = None  # {source_column, target_table, target_column}


class BulkDecisionRequest(BaseModel):
    decisions: list[DecisionRequest]


@router.get("/queue")
def get_validation_queue(
    project_id: str,
    batch_size: int = 10,
    db: Session = Depends(get_db),
) -> dict:
    """
    Return the next batch of relationships to validate, prioritized by impact.

    The queue is ordered:
    1. Certain (≥0.90) — fast confirmations
    2. High confidence (0.70–0.90)
    3. Medium (0.50–0.70) — review carefully
    4. Low/speculative — last

    Within each tier, relationships are grouped by source table.
    """
    service = ProjectMemoryService(db)

    relationships = service.get_inferred_relationships(project_id)
    if not relationships:
        raise HTTPException(
            status_code=404,
            detail="No inferred relationships found. Run inference first.",
        )

    decision_map = service.get_decision_map(project_id)
    queue = ValidationQueue(relationships, decision_map)

    return {
        "batch": [r.model_dump() for r in queue.get_next_batch(batch_size)],
        "progress": queue.progress(),
    }


@router.post("/decide", response_model=ValidationDecision)
def record_decision(
    project_id: str,
    req: DecisionRequest,
    db: Session = Depends(get_db),
) -> ValidationDecision:
    """
    Record an analyst decision about a single relationship.
    This is the primary way the analytical memory grows.
    """
    service = ProjectMemoryService(db)

    project = service.get_project(project_id)
    if not project:
        raise not_found("Project", project_id)

    decision = build_validation_decision(
        project_id=project_id,
        relationship_id=req.relationship_id,
        status=req.status,
        analyst_notes=req.analyst_notes,
        correction=req.correction,
    )
    service.record_decision(decision)
    return decision


@router.post("/decide/bulk")
def record_bulk_decisions(
    project_id: str,
    req: BulkDecisionRequest,
    db: Session = Depends(get_db),
) -> dict:
    """
    Record multiple validation decisions in a single request.
    Use for batch confirmations of high-confidence relationships.
    """
    service = ProjectMemoryService(db)

    project = service.get_project(project_id)
    if not project:
        raise not_found("Project", project_id)

    saved = 0
    for item in req.decisions:
        decision = build_validation_decision(
            project_id=project_id,
            relationship_id=item.relationship_id,
            status=item.status,
            analyst_notes=item.analyst_notes,
            correction=item.correction,
        )
        service.record_decision(decision)
        saved += 1

    return {"saved": saved}


@router.get("/decisions", response_model=list[ValidationDecision])
def get_decisions(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[ValidationDecision]:
    """Return all validation decisions for this project."""
    service = ProjectMemoryService(db)
    return service.get_decisions(project_id)
