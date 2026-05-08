from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SignalType(str, Enum):
    """
    The source of inference evidence for a relationship.
    Order reflects decreasing reliability in typical schemas.
    """

    STRUCTURAL = "structural"    # Explicit FK constraints or authoritative naming patterns
    LEXICAL = "lexical"          # Column/table name similarity
    STATISTICAL = "statistical"  # Value overlap analysis (requires live DB access)
    SEMANTIC = "semantic"        # Embedding-based semantic similarity (requires model)
    LLM = "llm"                  # LLM reasoning layer (requires API key)
    MANUAL = "manual"            # Analyst-defined relationship


class ConfidenceTier(str, Enum):
    """
    Human-readable confidence tier for a relationship.
    Used in UI to communicate trustworthiness clearly.
    """

    CERTAIN = "certain"          # ≥ 0.90 — explicit FK or multi-signal high agreement
    HIGH = "high"                # ≥ 0.70
    MEDIUM = "medium"            # ≥ 0.50
    LOW = "low"                  # ≥ 0.30
    SPECULATIVE = "speculative"  # < 0.30 — surface but do not default to confirmed

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceTier":
        if score >= 0.90:
            return cls.CERTAIN
        elif score >= 0.70:
            return cls.HIGH
        elif score >= 0.50:
            return cls.MEDIUM
        elif score >= 0.30:
            return cls.LOW
        else:
            return cls.SPECULATIVE


class SignalEvidence(BaseModel):
    """
    Evidence contributed by a single inference signal.
    Every relationship must be able to show exactly why it was inferred.
    """

    signal_type: SignalType
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0, description="Signal-specific reliability weight")
    reasoning: str = Field(description="Human-readable explanation of this signal's contribution")
    details: dict = Field(
        default_factory=dict,
        description="Signal-specific diagnostic data (e.g., similarity scores, matched patterns)",
    )


class InferredRelationship(BaseModel):
    """
    A candidate join relationship between two columns across two tables.

    Every relationship carries full provenance: which signals fired,
    what they found, and how confident the composite score is.
    Nothing is silently assumed.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_table: str
    source_column: str
    target_table: str
    target_column: str

    composite_score: float = Field(ge=0.0, le=1.0)
    confidence: ConfidenceTier
    evidence: list[SignalEvidence] = Field(default_factory=list)
    relationship_type: str = Field(
        default="many-to-one",
        description="Inferred cardinality: many-to-one, one-to-one, many-to-many",
    )
    inferred_at: datetime = Field(default_factory=datetime.utcnow)
    snapshot_id: Optional[str] = None

    @property
    def join_key(self) -> str:
        return f"{self.source_table}.{self.source_column} → {self.target_table}.{self.target_column}"

    def has_signal(self, signal_type: SignalType) -> bool:
        return any(e.signal_type == signal_type for e in self.evidence)

    def get_signal(self, signal_type: SignalType) -> Optional[SignalEvidence]:
        for e in self.evidence:
            if e.signal_type == signal_type:
                return e
        return None


class ValidationStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    DEFERRED = "deferred"


class ValidationDecision(BaseModel):
    """
    An analyst's explicit decision about an inferred relationship.
    These decisions form the core of the project's analytical memory.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    relationship_id: str
    status: ValidationStatus
    decided_at: datetime = Field(default_factory=datetime.utcnow)
    analyst_notes: Optional[str] = None

    # If the analyst corrects the relationship (wrong source/target), store correction
    corrected_source_column: Optional[str] = None
    corrected_target_table: Optional[str] = None
    corrected_target_column: Optional[str] = None

    @property
    def has_correction(self) -> bool:
        return any([
            self.corrected_source_column,
            self.corrected_target_table,
            self.corrected_target_column,
        ])
