"""Provider-independent, local column metadata index and hybrid retrieval."""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import re
from functools import lru_cache

import numpy as np
from sqlalchemy.orm import Session

from config import settings
from db.orm_models import ColumnSearchIndexORM, SemanticAnnotationORM
from models.schema import SchemaSnapshot

logger = logging.getLogger(__name__)


def _readable_name(name: str) -> str:
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    words = re.sub(r"[^A-Za-z0-9]+", " ", words).strip().lower().split()
    if words and words[-1] == "at":
        words[-1] = "date and time"
    elif words and words[-1] == "id":
        words[-1] = "identifier"
    return " ".join(words)


def _embedding_text(document: str) -> str:
    lines = document.splitlines()
    return "\n".join([lines[0], *(
        line for line in lines[1:] if "description:" in line or "note:" in line
    )])


@lru_cache(maxsize=2)
def _embedding_model(name: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(name, cache_folder=str(settings.data_dir / "models"))


def _model():
    if not settings.enable_vector_search or importlib.util.find_spec("sentence_transformers") is None:
        return None
    try:
        return _embedding_model(settings.embedding_model)
    except Exception:
        logger.exception("Local embedding model unavailable; column search will use lexical ranking")
        return None


def index_snapshot(db: Session, snapshot: SchemaSnapshot) -> list[ColumnSearchIndexORM]:
    """Refresh changed metadata records, reuse unchanged vectors, and drop removed columns."""
    project_id = snapshot.project_id
    existing = {
        (row.table_name, row.column_name): row
        for row in db.query(ColumnSearchIndexORM).filter_by(project_id=project_id).all()
    }
    annotations: dict[str, list[str]] = {}
    for item in db.query(SemanticAnnotationORM).filter_by(project_id=project_id).all():
        if item.target_type in ("table", "column"):
            annotations.setdefault(item.target_identifier, []).append(item.text)

    model = _model()
    model_name = settings.embedding_model if model is not None else None
    changed: list[ColumnSearchIndexORM] = []
    seen: set[tuple[str, str]] = set()
    for table in snapshot.tables:
        table_notes = annotations.get(table.name, [])
        for col in table.columns:
            key = (table.name, col.name)
            seen.add(key)
            parts = [
                f"{_readable_name(col.name)} in {_readable_name(table.name)}",
                f"Table: {table.name}",
                f"Column: {col.name}",
                f"Type: {col.raw_type}",
            ]
            if col.is_primary_key:
                parts.append("Primary key")
            if col.is_foreign_key and col.referenced_table:
                parts.append(f"References: {col.referenced_table}.{col.referenced_column or ''}")
            if table.analyst_note and not table.analyst_note.startswith("Row counts and column statistics pending"):
                parts.append(f"Table note: {table.analyst_note}")
            if col.analyst_note:
                parts.append(f"Column note: {col.analyst_note}")
            parts.extend(f"Table description: {note}" for note in table_notes)
            parts.extend(f"Column description: {note}" for note in annotations.get(f"{table.name}.{col.name}", []))
            document = "\n".join(parts)
            digest = hashlib.sha256(document.encode("utf-8")).hexdigest()
            row = existing.get(key)
            if row is None:
                row = ColumnSearchIndexORM(project_id=project_id, table_name=table.name, column_name=col.name,
                                           snapshot_id=snapshot.id, document=document, document_hash=digest)
                db.add(row)
                changed.append(row)
            elif row.document_hash != digest or (model_name and (row.model_name != model_name or row.embedding is None)):
                row.document = document
                row.document_hash = digest
                row.embedding = None
                row.model_name = None
                changed.append(row)
            row.snapshot_id = snapshot.id

    for key, row in existing.items():
        if key not in seen:
            db.delete(row)

    if model is not None and changed:
        try:
            vectors = model.encode([_embedding_text(row.document) for row in changed], normalize_embeddings=True,
                                   show_progress_bar=False)
            for row, vector in zip(changed, vectors):
                row.embedding = vector.tolist()
                row.model_name = model_name
        except Exception:
            logger.exception("Could not embed schema metadata; retaining lexical index")

    db.commit()
    return db.query(ColumnSearchIndexORM).filter_by(project_id=project_id).all()


def query_vector(term: str, rows: list[ColumnSearchIndexORM]) -> dict[tuple[str, str], float]:
    """Cosine similarity against normalized vectors. Missing local model yields no scores."""
    if not any(row.embedding for row in rows):
        return {}
    model = _model()
    if model is None:
        return {}
    try:
        indexed = [row for row in rows if row.embedding and row.model_name == settings.embedding_model]
        if not indexed:
            return {}
        vector = np.asarray(model.encode([term], normalize_embeddings=True, show_progress_bar=False)[0], dtype=np.float32)
        matrix = np.asarray([row.embedding for row in indexed], dtype=np.float32)
        similarities = matrix @ vector
        return {
            (row.table_name, row.column_name): float(score)
            for row, score in zip(indexed, similarities)
        }
    except Exception:
        logger.exception("Could not embed column search query; using lexical ranking")
        return {}
