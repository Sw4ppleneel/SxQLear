from __future__ import annotations

import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from api.projects import _score_term_against_snapshot
from core.schema import search_index
from db.session import Base
from models.schema import ColumnProfile, ColumnType, SchemaSnapshot, TableProfile


def column(name: str, sample_values: list[str] | None = None) -> ColumnProfile:
    return ColumnProfile(
        name=name, raw_type="TEXT", normalized_type=ColumnType.TEXT,
        is_nullable=True, is_primary_key=False, is_foreign_key=False,
        sample_values=sample_values or [],
    )


class FakeModel:
    def encode(self, texts, **kwargs):
        return np.array([
            [1.0, 0.0] if "renewal" in text.lower() or "subscription end" in text.lower()
            else [0.0, 1.0]
            for text in texts
        ])


def test_index_refresh_and_semantic_retrieval(monkeypatch):
    monkeypatch.setattr(search_index, "_model", lambda: FakeModel())
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = SchemaSnapshot(
            project_id="p1", connection_id="c1",
            tables=[TableProfile(name="accounts", columns=[
                column("subscription_end_at", ["private-customer-value"]), column("internal_code")
            ])],
        )
        rows = search_index.index_snapshot(db, first)
        assert len(rows) == 2
        assert all("private-customer-value" not in row.document for row in rows)
        scores = search_index.query_vector("renewal date", rows)
        documents = {(row.table_name, row.column_name): row.document for row in rows}
        matches = _score_term_against_snapshot("renewal date", first, 5, documents, scores)
        assert matches[0].column == "subscription_end_at"
        assert "semantic" in " ".join(matches[0].reasons)

        old_embedding = next(row.embedding for row in rows if row.column_name == "subscription_end_at")
        second = SchemaSnapshot(
            project_id="p1", connection_id="c1",
            tables=[TableProfile(name="accounts", columns=[column("subscription_end_at")])],
        )
        updated = search_index.index_snapshot(db, second)
        assert len(updated) == 1
        assert updated[0].snapshot_id == second.id
        assert updated[0].embedding == old_embedding
