from __future__ import annotations

import logging

import sqlalchemy as sa
from sqlalchemy import inspect

from config import settings
from core.schema.crawler import _normalize_column_type
from models.schema import ColumnProfile, ForeignKeyConstraint, TableProfile

logger = logging.getLogger(__name__)


def catalog_all_tables(engine: sa.Engine) -> list[TableProfile]:
    """
    Stage A of the staged crawl: build a TableProfile skeleton (columns,
    types, PK/FK, indexes — no row counts, no column stats, no sample
    values) for every table using SQLAlchemy's batched reflection API.

    This is the fix for the crawl's biggest structural cost: the previous
    design called inspector.get_columns()/get_pk_constraint()/
    get_foreign_keys()/get_indexes() once PER TABLE (4 round trips x N
    tables). get_multi_* issues one query per catalog view for ALL tables,
    so a 500-table database costs a handful of queries instead of ~2000.

    Runs in seconds even on wide schemas, and the result is immediately
    useful on its own: the schema graph and structural/lexical inference
    signals only need this — not row counts or column profiling — so the
    analyst sees a populated schema graph before any profiling has run.
    """
    inspector = inspect(engine)

    table_names = inspector.get_table_names()
    if len(table_names) > settings.max_tables_per_crawl:
        logger.warning(
            "Capping crawl at %d tables (found %d)",
            settings.max_tables_per_crawl,
            len(table_names),
        )
        table_names = table_names[: settings.max_tables_per_crawl]
    wanted = set(table_names)

    columns_by_table = inspector.get_multi_columns()
    pk_by_table = inspector.get_multi_pk_constraint()
    fks_by_table = inspector.get_multi_foreign_keys()
    indexes_by_table = inspector.get_multi_indexes()

    profiles: list[TableProfile] = []

    for key, columns_meta in columns_by_table.items():
        # Keys are (schema, table_name); schema is None when unqualified.
        table_name = key[1] if isinstance(key, tuple) else key
        if table_name not in wanted:
            continue

        pk_meta = pk_by_table.get(key, {})
        pk_columns = set(pk_meta.get("constrained_columns") or [])

        fk_meta = fks_by_table.get(key, [])
        fk_by_column: dict[str, tuple[str, str]] = {}
        for fk in fk_meta:
            for local_col, ref_col in zip(
                fk.get("constrained_columns", []), fk.get("referred_columns", [])
            ):
                fk_by_column[local_col] = (fk.get("referred_table", ""), ref_col)

        columns: list[ColumnProfile] = []
        for ordinal, col_meta in enumerate(columns_meta):
            col_name: str = col_meta["name"]
            fk_ref = fk_by_column.get(col_name)
            columns.append(
                ColumnProfile(
                    name=col_name,
                    raw_type=str(col_meta["type"]),
                    normalized_type=_normalize_column_type(str(col_meta["type"])),
                    is_nullable=bool(col_meta.get("nullable", True)),
                    is_primary_key=col_name in pk_columns,
                    is_foreign_key=fk_ref is not None,
                    referenced_table=fk_ref[0] if fk_ref else None,
                    referenced_column=fk_ref[1] if fk_ref else None,
                    ordinal_position=ordinal,
                )
            )

        fk_constraints = [
            ForeignKeyConstraint(
                constrained_columns=fk.get("constrained_columns", []),
                referred_table=fk.get("referred_table", ""),
                referred_columns=fk.get("referred_columns", []),
                name=fk.get("name"),
            )
            for fk in fk_meta
        ]

        index_meta = indexes_by_table.get(key, [])

        profiles.append(
            TableProfile(
                name=table_name,
                columns=columns,
                primary_keys=list(pk_columns),
                foreign_key_constraints=fk_constraints,
                index_names=[idx.get("name", "") for idx in index_meta if idx.get("name")],
                analyst_note="Row counts and column statistics pending — catalog stage only.",
            )
        )

    return profiles
