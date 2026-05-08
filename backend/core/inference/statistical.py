from __future__ import annotations

import logging
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import text

from models.relationship import SignalEvidence, SignalType
from models.schema import ColumnProfile, ColumnType

logger = logging.getLogger(__name__)

# Maximum rows to sample for overlap analysis.
# Keep this small — statistical inference is a supplementary signal, not a scan.
OVERLAP_SAMPLE_SIZE = 5_000


class StatisticalSignal:
    """
    Infers relationships by analyzing value overlap between columns.

    This signal requires a live connection to the target database.
    It executes read-only queries using bounded LIMIT clauses.

    Analyst consent is required before running statistical profiling:
    - It executes queries against the target DB
    - It may expose sample data values in evidence logs
    - It is controlled by the `enable_statistical_profiling` setting

    Overlap analysis is powerful for detecting undeclared FK relationships
    in legacy databases where constraints are not enforced at the DB level.
    """

    MIN_OVERLAP_THRESHOLD = 0.05

    def analyze(
        self,
        engine: sa.Engine,
        source_table: str,
        source_col: ColumnProfile,
        target_table: str,
        target_col: ColumnProfile,
    ) -> Optional[SignalEvidence]:
        """
        Compute value overlap between two columns using a sampled approach.

        Overlap ratio = |intersection(source_values, target_values)| / |source_distinct|

        High overlap (>70%) indicates the values in source_col are likely drawn
        from the value set in target_col — strong FK evidence.
        """
        # Skip expensive analysis for large text/blob types
        skip_types = {ColumnType.TEXT, ColumnType.JSON, ColumnType.BYTES}
        if source_col.normalized_type in skip_types or target_col.normalized_type in skip_types:
            return None

        try:
            with engine.connect() as conn:
                # Sample distinct values from source column
                src_result = conn.execute(
                    text(
                        f'SELECT DISTINCT CAST("{source_col.name}" AS VARCHAR) '
                        f'FROM "{source_table}" '
                        f'WHERE "{source_col.name}" IS NOT NULL '
                        f'LIMIT {OVERLAP_SAMPLE_SIZE}'
                    )
                )
                source_values = {str(row[0]) for row in src_result.fetchall()}

                if not source_values:
                    return None

                # Sample distinct values from target column
                tgt_result = conn.execute(
                    text(
                        f'SELECT DISTINCT CAST("{target_col.name}" AS VARCHAR) '
                        f'FROM "{target_table}" '
                        f'WHERE "{target_col.name}" IS NOT NULL '
                        f'LIMIT {OVERLAP_SAMPLE_SIZE}'
                    )
                )
                target_values = {str(row[0]) for row in tgt_result.fetchall()}

                if not target_values:
                    return None

            overlap = source_values & target_values
            overlap_ratio = len(overlap) / len(source_values)
            coverage_ratio = len(overlap) / len(target_values) if target_values else 0

            if overlap_ratio < self.MIN_OVERLAP_THRESHOLD:
                return None

            score = self._score_from_overlap(overlap_ratio, coverage_ratio)
            reasons = self._build_reasoning(
                overlap_ratio, coverage_ratio, len(overlap), len(source_values), len(target_values)
            )

            return SignalEvidence(
                signal_type=SignalType.STATISTICAL,
                score=round(score, 4),
                weight=0.9,
                reasoning=" | ".join(reasons),
                details={
                    "overlap_count": len(overlap),
                    "source_distinct_sample": len(source_values),
                    "target_distinct_sample": len(target_values),
                    "overlap_ratio": round(overlap_ratio, 4),
                    "coverage_ratio": round(coverage_ratio, 4),
                    "sample_size": OVERLAP_SAMPLE_SIZE,
                },
            )

        except Exception as exc:
            logger.debug(
                "Statistical analysis failed for %s.%s → %s.%s: %s",
                source_table, source_col.name, target_table, target_col.name, exc,
            )
            return None

    @staticmethod
    def _score_from_overlap(overlap_ratio: float, coverage_ratio: float) -> float:
        """
        Convert overlap and coverage ratios into a confidence score.

        High overlap (most source values exist in target) is necessary but not
        sufficient. Coverage (target values that appear in source) is also
        informative — a very wide target with small overlap may indicate a
        lookup table rather than a real FK.
        """
        # Weighted combination — overlap is the primary signal
        raw = overlap_ratio * 0.70 + coverage_ratio * 0.30
        # Clamp and apply a slight compression to avoid overconfidence from sampling
        return min(0.92, raw)

    @staticmethod
    def _build_reasoning(
        overlap_ratio: float,
        coverage_ratio: float,
        overlap_count: int,
        source_count: int,
        target_count: int,
    ) -> list[str]:
        reasons = [
            f"{overlap_count} of {source_count} sampled source values "
            f"exist in target ({overlap_ratio * 100:.1f}% overlap)"
        ]
        if coverage_ratio > 0.8:
            reasons.append(
                f"Source covers {coverage_ratio * 100:.1f}% of target value set "
                f"— consistent with a FK referencing a lookup/dimension table"
            )
        elif coverage_ratio < 0.1 and target_count > source_count * 5:
            reasons.append(
                f"Target has many more distinct values ({target_count}) than source "
                f"({source_count}) — may indicate a wide reference table"
            )
        return reasons
