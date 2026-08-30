from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Dialect


def quote_identifier(identifier: str, dialect: Dialect | None = None) -> str:
    """
    Dialect-aware identifier quoting for table/column names that get
    interpolated into raw SQL text.

    Bare f'"{name}"' quoting (the pattern this replaces) does not escape an
    embedded quote character, so a name containing `"` breaks out of the
    quoted identifier — this is the fix for that. Uses SQLAlchemy's own
    IdentifierPreparer, which already knows each dialect's escaping rules
    (e.g. doubling `"` for Postgres/SQLite, backtick-escaping for MySQL),
    rather than hand-rolling escaping per call site.
    """
    if dialect is None:
        dialect = postgresql.dialect()  # type: ignore[no-untyped-call]  # SQLAlchemy stub gap
    preparer = dialect.identifier_preparer
    return preparer.quote(sa.sql.quoted_name(identifier, quote=True))


def quote_qualified(*parts: str, dialect: Dialect | None = None) -> str:
    """Quote and join identifier parts with '.', e.g. quote_qualified("t", "c") -> '"t"."c"'."""
    return ".".join(quote_identifier(p, dialect=dialect) for p in parts)
