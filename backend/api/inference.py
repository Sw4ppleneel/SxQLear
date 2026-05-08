from __future__ import annotations

import httpx
import json as _json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.errors import not_found
from api.projects import _deserialize_connection_config
from config import settings
from core.inference.engine import InferenceEngine
from core.memory.project_memory import ProjectMemoryService
from core.schema.crawler import SchemaCrawler
from db.session import get_db
from models.relationship import (
    ConfidenceTier,
    InferredRelationship,
    SignalEvidence,
    SignalType,
    ValidationDecision,
    ValidationStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects/{project_id}/inference", tags=["inference"])


@router.post("", response_model=list[InferredRelationship])
def run_inference(
    project_id: str,
    use_statistical: bool = False,
    db: Session = Depends(get_db),
) -> list[InferredRelationship]:
    """
    Run the relationship inference pipeline on the latest schema snapshot.

    Returns a ranked list of candidate relationships with full evidence.
    Results are saved to project memory and returned.

    Args:
        use_statistical: If True, runs statistical overlap analysis against the
            live target DB. Requires explicit opt-in because it executes queries.
    """
    service = ProjectMemoryService(db)

    snapshot = service.get_latest_snapshot(project_id)
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail="No snapshot found. Run a schema crawl first.",
        )

    # Build target engine for statistical analysis if requested
    target_engine = None
    if use_statistical:
        config_dict = service.get_connection_config(project_id)
        if config_dict:
            try:
                config = _deserialize_connection_config(config_dict)
                crawler = SchemaCrawler(config)
                target_engine = crawler._get_engine()
            except Exception as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"Could not connect for statistical analysis: {exc}",
                )

    engine = InferenceEngine(target_engine=target_engine)
    relationships = engine.infer(snapshot)

    service.save_inferred_relationships(project_id, snapshot.id, relationships)
    return relationships


@router.get("", response_model=list[InferredRelationship])
def get_relationships(
    project_id: str,
    db: Session = Depends(get_db),
) -> list[InferredRelationship]:
    """Return all previously inferred relationships for this project."""
    service = ProjectMemoryService(db)

    project = service.get_project(project_id)
    if not project:
        raise not_found("Project", project_id)

    return service.get_inferred_relationships(project_id)


@router.get("/{relationship_id}", response_model=InferredRelationship)
def get_relationship(
    project_id: str,
    relationship_id: str,
    db: Session = Depends(get_db),
) -> InferredRelationship:
    """Return a single relationship with its full evidence."""
    service = ProjectMemoryService(db)
    relationships = service.get_inferred_relationships(project_id)
    for rel in relationships:
        if rel.id == relationship_id:
            return rel
    raise not_found("Relationship", relationship_id)


# ── Manual Relationships ──────────────────────────────────────────────────────

class ManualRelationshipRequest(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str = "many-to-one"
    reason: Optional[str] = None


@router.post("/manual", response_model=InferredRelationship, status_code=201)
def create_manual_relationship(
    project_id: str,
    req: ManualRelationshipRequest,
    db: Session = Depends(get_db),
) -> InferredRelationship:
    """
    Define a relationship manually. The analyst is the authority — it goes
    straight into confirmed state with SignalType.MANUAL evidence.

    Use this when you know two columns are related but the inference engine
    can't detect it (different names, business-logic join, no FK constraint).
    """
    service = ProjectMemoryService(db)

    snapshot = service.get_latest_snapshot(project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshot found. Run a crawl first.")

    # Validate tables and columns exist in snapshot
    src_table = snapshot.get_table(req.source_table)
    tgt_table = snapshot.get_table(req.target_table)
    if not src_table:
        raise HTTPException(status_code=422, detail=f"Table '{req.source_table}' not in snapshot")
    if not tgt_table:
        raise HTTPException(status_code=422, detail=f"Table '{req.target_table}' not in snapshot")
    if not src_table.get_column(req.source_column):
        raise HTTPException(status_code=422, detail=f"Column '{req.source_column}' not in '{req.source_table}'")
    if not tgt_table.get_column(req.target_column):
        raise HTTPException(status_code=422, detail=f"Column '{req.target_column}' not in '{req.target_table}'")

    reasoning = req.reason or f"Manually defined by analyst: {req.source_table}.{req.source_column} → {req.target_table}.{req.target_column}"

    rel = InferredRelationship(
        source_table=req.source_table,
        source_column=req.source_column,
        target_table=req.target_table,
        target_column=req.target_column,
        composite_score=1.0,
        confidence=ConfidenceTier.CERTAIN,
        relationship_type=req.relationship_type,
        snapshot_id=snapshot.id,
        evidence=[
            SignalEvidence(
                signal_type=SignalType.MANUAL,
                score=1.0,
                weight=1.0,
                reasoning=reasoning,
                details={"source": "analyst", "reason": req.reason or ""},
            )
        ],
    )

    service.save_inferred_relationships(project_id, snapshot.id, [rel])

    # Auto-confirm: analyst defining it manually = confirmed
    decision = ValidationDecision(
        project_id=project_id,
        relationship_id=rel.id,
        status=ValidationStatus.CONFIRMED,
        analyst_notes=req.reason,
    )
    from db.repositories.project_repo import ProjectRepository
    ProjectRepository(db).save_decision(decision)

    return rel


# ── LLM-Assisted Suggestion ───────────────────────────────────────────────────

class SuggestRequest(BaseModel):
    intent: str
    """
    What the analyst is trying to build or understand.
    Example: "I want to track which patients renewed and match their session history"
    The LLM uses this to focus its suggestions on relevant joins.
    """
    max_suggestions: int = 8


class SuggestedJoin(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str
    reasoning: str
    confidence: str  # "certain" | "high" | "medium" | "speculative"


class SuggestResponse(BaseModel):
    suggestions: list[SuggestedJoin]
    llm_summary: str
    model_used: str


@router.post("/suggest", response_model=SuggestResponse)
def suggest_relationships(
    project_id: str,
    req: SuggestRequest,
    db: Session = Depends(get_db),
) -> SuggestResponse:
    """
    Use an LLM to scan column headers across all tables and suggest joins
    relevant to the analyst's stated intent.

    The LLM sees only table names, column names, types, and row counts —
    never actual data values. It reasons about semantic meaning from names alone.

    Requires OPENAI_API_KEY or ANTHROPIC_API_KEY in settings.
    """
    if not settings.openai_api_key and not settings.anthropic_api_key:
        raise HTTPException(
            status_code=422,
            detail=(
                "No LLM API key configured. Add OPENAI_API_KEY or ANTHROPIC_API_KEY "
                "to backend/.env to use AI suggestions."
            ),
        )

    service = ProjectMemoryService(db)
    snapshot = service.get_latest_snapshot(project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshot found. Run a crawl first.")

    # Build a compact schema digest — table names, column names, types, row counts
    # Never sends actual data values to the LLM
    schema_digest = _build_schema_digest(snapshot)

    prompt = _build_suggest_prompt(req.intent, schema_digest, req.max_suggestions)

    if settings.openai_api_key:
        raw = _call_openai(prompt, settings.openai_api_key)
        model_used = "openai/gpt-4o-mini"
    else:
        raw = _call_anthropic(prompt, settings.anthropic_api_key)
        model_used = "anthropic/claude-3-haiku"

    suggestions, summary = _parse_llm_response(raw)
    return SuggestResponse(suggestions=suggestions, llm_summary=summary, model_used=model_used)


def _build_schema_digest(snapshot) -> str:
    """Compact schema summary for LLM context. No data values."""
    lines = []
    for table in snapshot.tables:
        row_info = f" (~{table.row_count:,} rows)" if table.row_count else ""
        lines.append(f"\nTABLE: {table.name}{row_info}")
        for col in table.columns:
            flags = []
            if col.is_primary_key: flags.append("PK")
            if col.is_foreign_key: flags.append("FK")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"  {col.name}: {col.raw_type}{flag_str}")
    return "\n".join(lines)


def _build_suggest_prompt(intent: str, schema_digest: str, max_suggestions: int) -> str:
    return f"""You are a database analyst assistant. You have been given a database schema and an analyst's goal.
Your job: identify the most useful column-level join relationships to achieve the analyst's goal.

ANALYST INTENT:
{intent}

DATABASE SCHEMA (table names, column names, types — no data values):
{schema_digest}

TASK:
Return up to {max_suggestions} specific join suggestions. Focus only on joins relevant to the analyst's intent.
Include both obvious FK-style joins AND semantic/business-logic joins (e.g., two columns with different names that represent the same entity).

Respond with valid JSON only, no markdown, no explanation outside the JSON:
{{
  "summary": "One paragraph explaining the suggested join strategy for the analyst's goal",
  "suggestions": [
    {{
      "source_table": "table_name",
      "source_column": "column_name",
      "target_table": "table_name",
      "target_column": "column_name",
      "relationship_type": "many-to-one",
      "confidence": "high",
      "reasoning": "Why this join is relevant to the stated intent"
    }}
  ]
}}

relationship_type must be one of: many-to-one, one-to-one, many-to-many
confidence must be one of: certain, high, medium, speculative
"""


def _call_openai(prompt: str, api_key: str) -> str:
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def _call_anthropic(prompt: str, api_key: str) -> str:
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": "claude-3-haiku-20240307",
                "max_tokens": 2048,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"]


def _parse_llm_response(raw: str) -> tuple[list[SuggestedJoin], str]:
    try:
        data = _json.loads(raw)
    except Exception:
        logger.warning("LLM response was not valid JSON: %s", raw[:200])
        return [], "Could not parse LLM response."

    summary = data.get("summary", "")
    suggestions = []
    valid_confidence = {"certain", "high", "medium", "speculative"}
    valid_rel_types = {"many-to-one", "one-to-one", "many-to-many"}

    for item in data.get("suggestions", []):
        try:
            suggestions.append(SuggestedJoin(
                source_table=item["source_table"],
                source_column=item["source_column"],
                target_table=item["target_table"],
                target_column=item["target_column"],
                relationship_type=item.get("relationship_type", "many-to-one") if item.get("relationship_type") in valid_rel_types else "many-to-one",
                reasoning=item.get("reasoning", ""),
                confidence=item.get("confidence", "medium") if item.get("confidence") in valid_confidence else "medium",
            ))
        except (KeyError, Exception) as e:
            logger.debug("Skipping malformed suggestion: %s", e)

    return suggestions, summary
