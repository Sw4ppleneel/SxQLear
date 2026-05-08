from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import sqlalchemy as sa

from config import settings
from core.inference.lexical import LexicalSignal
from core.inference.statistical import StatisticalSignal
from core.inference.structural import StructuralSignal
from models.relationship import (
    ConfidenceTier,
    InferredRelationship,
    SignalEvidence,
    SignalType,
)
from models.schema import ColumnProfile, SchemaSnapshot, TableProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandidatePair:
    """
    A candidate join: source column in source table may reference target column in target table.
    Immutable and hashable for deduplication.
    """

    source_table: str
    source_column: str
    target_table: str
    target_column: str

    @property
    def key(self) -> str:
        return f"{self.source_table}.{self.source_column}→{self.target_table}.{self.target_column}"


class InferenceEngine:
    """
    Multi-signal relationship inference engine.

    Philosophy:
    ─────────────────────────────────────────────────────────────────────────────
    1. No silent assumptions. Every inferred relationship carries full evidence.
    2. Hybrid approach: symbolic patterns + lexical similarity + statistical overlap.
    3. Confidence is bounded, explicitly reasoned, and always shown to the analyst.
    4. The engine never mutates the SchemaSnapshot it analyzes.
    5. Every signal is independently inspectable.

    Signal weights (configurable):
    ─────────────────────────────────────────────────────────────────────────────
    STRUCTURAL  0.45 — Highest authority: FK constraints + naming conventions
    LEXICAL     0.30 — Reliable: identifier similarity analysis
    STATISTICAL 0.15 — Requires live DB access; opt-in only
    SEMANTIC    0.10 — Requires embedding model; opt-in only

    Composite score = weighted_sum(active_signals) / total_active_weight
    This normalizes correctly when not all signals are available.
    """

    DEFAULT_SIGNAL_WEIGHTS: dict[SignalType, float] = {
        SignalType.STRUCTURAL: 0.45,
        SignalType.LEXICAL: 0.30,
        SignalType.STATISTICAL: 0.15,
        SignalType.SEMANTIC: 0.10,
        SignalType.LLM: 0.00,    # LLM evidence modifies reasoning but doesn't affect score
    }

    def __init__(
        self,
        signal_weights: Optional[dict[SignalType, float]] = None,
        target_engine: Optional[sa.Engine] = None,
    ) -> None:
        """
        Args:
            signal_weights: Override default signal weights.
            target_engine: Live DB engine for statistical analysis (opt-in).
                If None, statistical signal is skipped.
        """
        self._weights = signal_weights or self.DEFAULT_SIGNAL_WEIGHTS
        self._target_engine = target_engine

        self._structural = StructuralSignal()
        self._lexical = LexicalSignal()
        self._statistical = StatisticalSignal() if target_engine is not None else None

    def infer(self, snapshot: SchemaSnapshot) -> list[InferredRelationship]:
        """
        Run full inference pipeline on a SchemaSnapshot.

        Returns:
            List of InferredRelationship, sorted by composite_score descending.
            Only relationships above settings.min_inference_score are returned.
        """
        logger.info(
            "Starting inference on snapshot %s (%d tables)",
            snapshot.id,
            len(snapshot.tables),
        )

        candidates = self._generate_candidates(snapshot)
        logger.debug("Generated %d candidate pairs", len(candidates))

        relationships: list[InferredRelationship] = []

        for candidate in candidates:
            source_table = snapshot.get_table(candidate.source_table)
            target_table = snapshot.get_table(candidate.target_table)

            if source_table is None or target_table is None:
                continue

            source_col = source_table.get_column(candidate.source_column)
            target_col = target_table.get_column(candidate.target_column)

            if source_col is None or target_col is None:
                continue

            evidence = self._collect_evidence(
                candidate, source_table, target_table, source_col, target_col
            )

            composite = self._compute_composite_score(evidence)

            if composite < settings.min_inference_score:
                continue

            rel = InferredRelationship(
                source_table=candidate.source_table,
                source_column=candidate.source_column,
                target_table=candidate.target_table,
                target_column=candidate.target_column,
                composite_score=round(composite, 4),
                confidence=ConfidenceTier.from_score(composite),
                evidence=evidence,
                relationship_type=self._infer_cardinality(source_col, target_col),
                snapshot_id=snapshot.id,
            )
            relationships.append(rel)

        # Deduplicate: if we somehow generated the same pair from multiple paths, keep highest
        relationships = self._deduplicate(relationships)
        relationships.sort(key=lambda r: r.composite_score, reverse=True)

        logger.info(
            "Inference complete: %d relationships found (threshold: %.2f)",
            len(relationships),
            settings.min_inference_score,
        )
        return relationships

    # ── Candidate Generation ──────────────────────────────────────────────────

    def _generate_candidates(self, snapshot: SchemaSnapshot) -> list[CandidatePair]:
        """
        Generate candidate column pairs for relationship analysis.

        Strategy:
        1. Always include all explicitly declared FK pairs (highest priority).
        2. ID-suffix columns in one table paired with PK columns in potential target.
        3. Column name similarity across tables (via lexical signal threshold).

        We intentionally over-generate candidates and let signal scoring filter them.
        This ensures we don't miss relationships by failing to generate the candidate.
        """
        candidates: set[CandidatePair] = set()
        table_map: dict[str, TableProfile] = {t.name: t for t in snapshot.tables}

        for table in snapshot.tables:
            for col in table.columns:

                # ── Path 1: Explicit FK constraints ───────────────────────────
                if col.is_foreign_key and col.referenced_table:
                    ref_table = table_map.get(col.referenced_table)
                    ref_col_name = col.referenced_column or self._find_pk(ref_table)
                    if ref_table and ref_col_name:
                        candidates.add(CandidatePair(
                            source_table=table.name,
                            source_column=col.name,
                            target_table=col.referenced_table,
                            target_column=ref_col_name,
                        ))

                # ── Path 2: ID-suffix naming patterns ─────────────────────────
                if self._is_fk_candidate_name(col.name) and not col.is_primary_key:
                    for target_name, target_table in table_map.items():
                        if target_name == table.name:
                            continue
                        if self._name_suggests_reference(col.name, target_name):
                            pk_col_name = self._find_pk(target_table)
                            if pk_col_name:
                                candidates.add(CandidatePair(
                                    source_table=table.name,
                                    source_column=col.name,
                                    target_table=target_name,
                                    target_column=pk_col_name,
                                ))

        logger.debug("Generated %d unique candidate pairs", len(candidates))
        return list(candidates)

    @staticmethod
    def _is_fk_candidate_name(col_name: str) -> bool:
        """Does this column name pattern suggest it might be a foreign key?"""
        lower = col_name.lower()
        return (
            lower.endswith("_id")
            or lower.endswith("_key")
            or lower.endswith("_fk")
            or lower.endswith("_ref")
            or (lower.endswith("id") and len(lower) > 3 and not lower == "id")
        )

    @staticmethod
    def _name_suggests_reference(col_name: str, table_name: str) -> bool:
        """
        Does 'col_name' lexically suggest a reference to 'table_name'?
        Examples: customer_id → customers, order_id → orders
        """
        import re
        lower = col_name.lower()
        tbl_lower = table_name.lower()

        # Strip ID suffix variations
        stripped = re.sub(r"(_id|_key|_fk|_ref|id)$", "", lower).strip("_")
        if not stripped:
            return False

        return tbl_lower in (stripped, stripped + "s", stripped + "es", stripped[:-1])

    @staticmethod
    def _find_pk(table: Optional[TableProfile]) -> Optional[str]:
        """Return the first PK column name, falling back to 'id' if present."""
        if table is None:
            return None
        if table.primary_keys:
            return table.primary_keys[0]
        for col in table.columns:
            if col.name.lower() == "id":
                return col.name
        return None

    # ── Signal Collection ─────────────────────────────────────────────────────

    def _collect_evidence(
        self,
        candidate: CandidatePair,
        source_table: TableProfile,
        target_table: TableProfile,
        source_col: ColumnProfile,
        target_col: ColumnProfile,
    ) -> list[SignalEvidence]:
        evidence: list[SignalEvidence] = []

        # Structural signal (always run)
        structural = self._structural.analyze(
            candidate.source_table, source_col, candidate.target_table, target_col
        )
        if structural:
            evidence.append(structural)

        # Lexical signal (always run)
        lexical = self._lexical.analyze(
            candidate.source_table, source_col, candidate.target_table, target_col
        )
        if lexical:
            evidence.append(lexical)

        # Statistical signal (opt-in, requires live DB access)
        if self._statistical and self._target_engine and settings.enable_statistical_profiling:
            statistical = self._statistical.analyze(
                self._target_engine,
                candidate.source_table,
                source_col,
                candidate.target_table,
                target_col,
            )
            if statistical:
                evidence.append(statistical)

        return evidence

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _compute_composite_score(self, evidence: list[SignalEvidence]) -> float:
        """
        Weighted combination of signal scores.

        The weight applied per evidence item is the product of:
        - The global signal-type weight (architectural priority)
        - The evidence's own weight (signal-instance reliability)

        Normalizing by the sum of active weights ensures the score is well-defined
        when only a subset of signals fired.
        """
        if not evidence:
            return 0.0

        weighted_scores = 0.0
        total_weight = 0.0

        for ev in evidence:
            signal_weight = self._weights.get(ev.signal_type, 0.05)
            effective_weight = signal_weight * ev.weight
            weighted_scores += ev.score * effective_weight
            total_weight += effective_weight

        if total_weight == 0:
            return 0.0

        return min(1.0, weighted_scores / total_weight)

    @staticmethod
    def _infer_cardinality(source_col: ColumnProfile, target_col: ColumnProfile) -> str:
        """
        Infer relationship cardinality from column characteristics.
        This is a heuristic — analyst should validate for complex cases.
        """
        if target_col.is_primary_key:
            if source_col.is_primary_key:
                return "one-to-one"
            # Selectivity check: if source has near-unique values, might be one-to-one
            if source_col.selectivity and source_col.selectivity > 0.95:
                return "one-to-one"
            return "many-to-one"
        return "many-to-many"

    @staticmethod
    def _deduplicate(relationships: list[InferredRelationship]) -> list[InferredRelationship]:
        """Remove duplicate relationships, keeping the highest-scoring version."""
        seen: dict[str, InferredRelationship] = {}
        for rel in relationships:
            key = f"{rel.source_table}.{rel.source_column}→{rel.target_table}.{rel.target_column}"
            if key not in seen or rel.composite_score > seen[key].composite_score:
                seen[key] = rel
        return list(seen.values())
