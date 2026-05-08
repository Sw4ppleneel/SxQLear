from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.errors import not_found
from core.dataset.constructor import DatasetConstructor
from core.dataset.sql_generator import SQLGenerator
from core.memory.project_memory import ProjectMemoryService
from db.session import get_db
from models.dataset import DatasetPlan, DatasetPlanStatus, FilterCondition
from models.relationship import ValidationStatus

router = APIRouter(prefix="/projects/{project_id}/datasets", tags=["datasets"])


class BuildDatasetRequest(BaseModel):
    name: str
    description: str
    base_table: str
    include_tables: list[str]
    filters: Optional[list[FilterCondition]] = None
    grain_description: Optional[str] = None


@router.post("", response_model=DatasetPlan, status_code=201)
def build_dataset_plan(
    project_id: str,
    req: BuildDatasetRequest,
    db: Session = Depends(get_db),
) -> DatasetPlan:
    """
    Construct a provenance-aware DatasetPlan from confirmed relationships.

    Only confirmed relationships are used for joins. If a required join
    has not been confirmed, it will be excluded and a warning will note the gap.
    """
    service = ProjectMemoryService(db)

    project = service.get_project(project_id)
    if not project:
        raise not_found("Project", project_id)

    snapshot = service.get_latest_snapshot(project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshot found. Run a crawl first.")

    # Only use confirmed relationships in dataset plans
    all_relationships = service.get_inferred_relationships(project_id)
    decision_map = service.get_decision_map(project_id)
    confirmed_ids = {rid for rid, s in decision_map.items() if s == ValidationStatus.CONFIRMED}
    confirmed_relationships = [r for r in all_relationships if r.id in confirmed_ids]

    constructor = DatasetConstructor()
    plan = constructor.build_plan(
        project_id=project_id,
        name=req.name,
        description=req.description,
        base_table=req.base_table,
        snapshot=snapshot,
        confirmed_relationships=confirmed_relationships,
        selected_tables=req.include_tables,
        filters=req.filters,
        grain_description=req.grain_description,
    )

    # Generate SQL immediately
    generator = SQLGenerator()
    plan.generated_sql = generator.generate(plan)
    from datetime import datetime
    plan.sql_generated_at = datetime.utcnow()

    from db.repositories.project_repo import ProjectRepository
    repo = ProjectRepository(db)
    repo.save_dataset_plan(plan)

    return plan


@router.get("", response_model=list[dict])
def list_dataset_plans(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[dict]:
    """List all dataset plans for this project."""
    from db.repositories.project_repo import ProjectRepository
    repo = ProjectRepository(db)
    orms = repo.get_dataset_plans(project_id)
    return [{"id": o.id, "name": o.name, "status": o.status, "created_at": str(o.created_at)} for o in orms]


@router.get("/{plan_id}", response_model=DatasetPlan)
def get_dataset_plan(
    project_id: str,
    plan_id: str,
    db: Session = Depends(get_db),
) -> DatasetPlan:
    from db.repositories.project_repo import ProjectRepository
    repo = ProjectRepository(db)
    plan = repo.get_dataset_plan(plan_id)
    if not plan or plan.project_id != project_id:
        raise not_found("DatasetPlan", plan_id)
    return plan


@router.post("/{plan_id}/generate-sql")
def generate_sql(
    project_id: str,
    plan_id: str,
    db: Session = Depends(get_db),
) -> dict:
    """(Re)generate SQL for a dataset plan."""
    from db.repositories.project_repo import ProjectRepository
    repo = ProjectRepository(db)
    plan = repo.get_dataset_plan(plan_id)
    if not plan or plan.project_id != project_id:
        raise not_found("DatasetPlan", plan_id)

    generator = SQLGenerator()
    sql = generator.generate(plan)
    return {"sql": sql}
