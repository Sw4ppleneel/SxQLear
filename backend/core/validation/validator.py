from __future__ import annotations

import logging
from typing import Optional

from models.relationship import (
    InferredRelationship,
    ValidationDecision,
    ValidationStatus,
)

logger = logging.getLogger(__name__)


class ValidationQueue:
    """
    Manages the ordered queue of relationships awaiting analyst review.

    Design principles:
    ─────────────────────────────────────────────────────────────────────────────
    - Prioritize high-impact, uncertain relationships first.
    - Batch similar relationships to reduce fatigue (same table cluster).
    - Never present the same relationship twice without context.
    - Every decision is immediately available to downstream processes.

    The queue is not persisted — it is rebuilt each time from the relationships
    and the decision map stored in project memory. This means the queue always
    reflects the current state of knowledge.
    """

    def __init__(
        self,
        relationships: list[InferredRelationship],
        decision_map: dict[str, ValidationStatus],
    ) -> None:
        self._relationships = relationships
        self._decision_map = decision_map

    @property
    def pending(self) -> list[InferredRelationship]:
        """All relationships that have not yet been decided."""
        return [r for r in self._relationships if r.id not in self._decision_map]

    @property
    def confirmed(self) -> list[InferredRelationship]:
        decided = {
            rid for rid, s in self._decision_map.items() if s == ValidationStatus.CONFIRMED
        }
        return [r for r in self._relationships if r.id in decided]

    @property
    def rejected(self) -> list[InferredRelationship]:
        decided = {
            rid for rid, s in self._decision_map.items() if s == ValidationStatus.REJECTED
        }
        return [r for r in self._relationships if r.id in decided]

    def get_next_batch(self, size: int = 10) -> list[InferredRelationship]:
        """
        Return the next batch of relationships to validate, ordered by priority.

        Priority ordering:
        1. Explicit FK relationships (score >= 0.90) — fast to confirm, high value
        2. High-confidence inferred (0.70–0.90) — likely correct, efficient to review
        3. Medium-confidence (0.50–0.70) — need careful review
        4. Low/speculative (< 0.50) — review last

        Within each tier, relationships are grouped by source table to reduce
        context switching for the analyst.
        """
        pending = self.pending

        # Group into priority tiers
        certain = [r for r in pending if r.composite_score >= 0.90]
        high = [r for r in pending if 0.70 <= r.composite_score < 0.90]
        medium = [r for r in pending if 0.50 <= r.composite_score < 0.70]
        low = [r for r in pending if r.composite_score < 0.50]

        # Sort each tier by source table for grouping
        for tier in (certain, high, medium, low):
            tier.sort(key=lambda r: (r.source_table, -r.composite_score))

        ordered = certain + high + medium + low
        return ordered[:size]

    def progress(self) -> dict:
        """Return a progress summary for display."""
        total = len(self._relationships)
        pending_count = len(self.pending)
        decided_count = total - pending_count

        return {
            "total": total,
            "decided": decided_count,
            "pending": pending_count,
            "confirmed": len(self.confirmed),
            "rejected": len(self.rejected),
            "completion_pct": round(decided_count / total * 100, 1) if total > 0 else 0.0,
        }


def build_validation_decision(
    project_id: str,
    relationship_id: str,
    status: ValidationStatus,
    analyst_notes: Optional[str] = None,
    correction: Optional[dict] = None,
) -> ValidationDecision:
    """
    Factory function for creating a ValidationDecision.
    Centralizes construction to ensure all required fields are set.
    """
    return ValidationDecision(
        project_id=project_id,
        relationship_id=relationship_id,
        status=status,
        analyst_notes=analyst_notes,
        corrected_source_column=correction.get("source_column") if correction else None,
        corrected_target_table=correction.get("target_table") if correction else None,
        corrected_target_column=correction.get("target_column") if correction else None,
    )
