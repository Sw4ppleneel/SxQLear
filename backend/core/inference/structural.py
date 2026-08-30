from __future__ import annotations

import logging
from typing import Optional

from models.relationship import (
    ConfidenceTier,
    InferredRelationship,
    SignalEvidence,
    SignalType,
)
from models.schema import ColumnProfile, TableProfile

logger = logging.getLogger(__name__)


class StructuralSignal:
    """
    Infers relationships from structural features of the schema.

    This is the highest-weight signal because structural evidence is authoritative:
    - An explicit FK constraint is nearly certain (score: 0.97)
    - Naming conventions (entity_id → entities.id) are reliable heuristics

    Type compatibility is checked as a modifier — a type mismatch significantly
    reduces confidence because it suggests the naming similarity is coincidental.
    """

    def analyze(
        self,
        source_table: str,
        source_col: ColumnProfile,
        target_table: str,
        target_col: ColumnProfile,
    ) -> Optional[SignalEvidence]:
        reasons: list[str] = []
        score = 0.0
        weight = 1.0

        # ── Explicit FK constraint ─────────────────────────────────────────────
        if (
            source_col.is_foreign_key
            and source_col.referenced_table == target_table
            and source_col.referenced_column == target_col.name
        ):
            score = 0.97
            weight = 1.0
            reasons.append(
                f"Explicit FK constraint: {source_table}.{source_col.name} "
                f"→ {target_table}.{target_col.name}"
            )

        else:
            # ── Naming convention analysis ─────────────────────────────────────
            src_lower = source_col.name.lower()
            tgt_table_lower = target_table.lower()

            # Pattern: column ends with _id, target table matches prefix
            if src_lower.endswith("_id"):
                prefix = src_lower[:-3]  # strip _id
                if tgt_table_lower in (prefix, prefix + "s", prefix + "es"):
                    score = 0.78
                    weight = 0.85
                    reasons.append(
                        f"Naming convention: '{source_col.name}' suffix '_id' "
                        f"matches table '{target_table}'"
                    )

            # Pattern: column is exactly <table_singular>id (no underscore)
            elif src_lower.endswith("id") and len(src_lower) > 2:
                prefix = src_lower[:-2]
                if tgt_table_lower in (prefix, prefix + "s", prefix + "es"):
                    score = 0.65
                    weight = 0.75
                    reasons.append(
                        f"Naming convention: '{source_col.name}' (no underscore) "
                        f"suggests reference to '{target_table}'"
                    )

            # Pattern: source column is a PK in source → target has matching _id
            if score == 0.0 and target_col.is_foreign_key:
                if (
                    target_col.referenced_table == source_table
                    and target_col.referenced_column == source_col.name
                ):
                    score = 0.97
                    weight = 1.0
                    reasons.append(
                        f"Reverse FK constraint: {target_table}.{target_col.name} "
                        f"→ {source_table}.{source_col.name}"
                    )

        if score == 0.0:
            return None

        # ── Type compatibility modifier ──────────────────────────────────────
        # A hard mismatch (e.g. a date column vs. a boolean column) means the
        # name match is very likely coincidental — exclude it outright rather
        # than merely discounting it, since a discount alone (0.78 * 0.30 =
        # 0.234) can still clear settings.min_inference_score (0.20) and
        # surface as an inferred relationship. A soft mismatch (integer vs.
        # string, common for legacy-DB ID columns) is still just discounted.
        compatibility = self._type_compatibility(source_col, target_col)
        if compatibility == "hard_mismatch":
            return None
        elif compatibility == "soft_mismatch":
            score *= 0.30
            reasons.append(
                f"⚠ Type mismatch: {source_col.raw_type} vs {target_col.raw_type} "
                f"— confidence heavily reduced"
            )
        else:
            reasons.append(
                f"Types compatible: {source_col.raw_type} / {target_col.raw_type}"
            )

        # ── PK bonus ──────────────────────────────────────────────────────────
        if target_col.is_primary_key:
            score = min(1.0, score + 0.05)
            reasons.append(f"Target column '{target_col.name}' is a primary key")

        return SignalEvidence(
            signal_type=SignalType.STRUCTURAL,
            score=round(score, 4),
            weight=weight,
            reasoning=" | ".join(reasons),
            details={
                "has_explicit_fk": source_col.is_foreign_key,
                "source_type": source_col.raw_type,
                "target_type": target_col.raw_type,
                "target_is_pk": target_col.is_primary_key,
            },
        )

    @staticmethod
    def _type_compatibility(a: ColumnProfile, b: ColumnProfile) -> str:
        """
        Classify two column types' compatibility for a join as one of:
        "compatible", "soft_mismatch" (discount but allow), or
        "hard_mismatch" (exclude — see caller).
        """
        from models.schema import ColumnType

        integer_like = {ColumnType.INTEGER, ColumnType.BIGINT}
        string_like = {ColumnType.VARCHAR, ColumnType.TEXT}
        numeric_like = {ColumnType.FLOAT, ColumnType.DECIMAL}

        def category(col: ColumnProfile) -> str:
            if col.normalized_type in integer_like:
                return "integer"
            if col.normalized_type in string_like:
                return "string"
            if col.normalized_type in numeric_like:
                return "numeric"
            if col.normalized_type == ColumnType.UUID:
                return "uuid"
            return "other"

        cat_a = category(a)
        cat_b = category(b)

        # Same category → compatible
        if cat_a == cat_b:
            return "compatible"
        # Integer IDs and varchar IDs are sometimes mixed (legacy DBs) —
        # plausible enough to keep, just discounted.
        if {cat_a, cat_b} <= {"integer", "string"}:
            return "soft_mismatch"
        return "hard_mismatch"
