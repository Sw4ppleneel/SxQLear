from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional

from models.relationship import SignalEvidence, SignalType
from models.schema import ColumnProfile, TableProfile


def _tokenize(identifier: str) -> list[str]:
    """
    Split a database identifier into semantic tokens.
    Handles snake_case, camelCase, and PascalCase.

    Examples:
        customer_order_id → ['customer', 'order', 'id']
        customerOrderId   → ['customer', 'order', 'id']
        UserID            → ['user', 'id']
    """
    # Insert underscore before uppercase runs (camelCase → snake_case)
    identifier = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", identifier)
    identifier = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", identifier)
    return [t.lower() for t in re.split(r"[_\s]+", identifier) if t]


def _jaccard_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union


def _sequence_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _identifier_similarity(a: str, b: str) -> float:
    """
    Composite similarity score between two identifiers.
    Combines token-level Jaccard with character-level sequence matching.
    """
    tokens_a = set(_tokenize(a))
    tokens_b = set(_tokenize(b))
    jaccard = _jaccard_similarity(tokens_a, tokens_b)
    sequence = _sequence_similarity(a, b)
    return 0.55 * jaccard + 0.45 * sequence


class LexicalSignal:
    """
    Infers relationships from lexical similarity between column and table names.

    Three complementary sub-signals:
    1. Column-to-column: direct name similarity (e.g., user_id vs user_id)
    2. Column-to-table: source column name vs target table name coherence
       (e.g., "customer_id" is lexically close to table "customers")
    3. PK pattern: source column ends with _id / id AND target column is a PK

    All three contribute to a composite score. The evidence includes exact
    similarity values so analysts can inspect why the inference fired.
    """

    MINIMUM_SCORE = 0.38  # Below this, lexical evidence is not reliable enough to include

    def analyze(
        self,
        source_table: str,
        source_col: ColumnProfile,
        target_table: str,
        target_col: ColumnProfile,
    ) -> Optional[SignalEvidence]:
        reasons: list[str] = []

        src_col_name = source_col.name
        tgt_col_name = target_col.name

        # ── Sub-signal 1: Column name similarity ──────────────────────────────
        col_col_sim = _identifier_similarity(src_col_name, tgt_col_name)

        # ── Sub-signal 2: Source column → target table coherence ──────────────
        # Strip common suffixes before comparing to table name
        src_stripped = re.sub(r"(_id|_key|_fk|_ref|id)$", "", src_col_name.lower()).strip("_")
        col_table_sim = max(
            _identifier_similarity(src_col_name, target_table),
            _identifier_similarity(src_stripped, target_table),
        )

        # ── Sub-signal 3: ID suffix + PK target pattern ───────────────────────
        pk_pattern_score = 0.0
        if target_col.is_primary_key and re.search(r"(id|key|fk|ref)$", src_col_name.lower()):
            pk_pattern_score = 0.82
            reasons.append(
                f"'{src_col_name}' has ID-like suffix and "
                f"'{tgt_col_name}' is a primary key — strong lexical pattern"
            )

        # ── Composite ─────────────────────────────────────────────────────────
        composite = max(
            col_col_sim * 0.45 + col_table_sim * 0.55,
            pk_pattern_score,
        )

        if composite < self.MINIMUM_SCORE:
            return None

        # Build human-readable evidence
        if col_table_sim > 0.45:
            reasons.append(
                f"Column '{src_col_name}' is lexically similar to table "
                f"'{target_table}' (score: {col_table_sim:.2f})"
            )
        if col_col_sim > 0.55:
            reasons.append(
                f"Column names '{src_col_name}' ↔ '{tgt_col_name}' are similar "
                f"(score: {col_col_sim:.2f})"
            )
        if not reasons:
            reasons.append(f"Lexical composite score: {composite:.2f}")

        # Weight reflects how strong the pattern is
        weight = 0.95 if pk_pattern_score > 0 else min(0.85, composite + 0.1)

        return SignalEvidence(
            signal_type=SignalType.LEXICAL,
            score=round(composite, 4),
            weight=round(weight, 4),
            reasoning=" | ".join(reasons),
            details={
                "col_col_similarity": round(col_col_sim, 4),
                "col_table_similarity": round(col_table_sim, 4),
                "pk_pattern_score": round(pk_pattern_score, 4),
                "source_stripped": src_stripped,
            },
        )
