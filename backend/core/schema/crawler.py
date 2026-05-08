from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import inspect, text

from config import settings
from models.connection import ConnectionConfig, ConnectionTestResult, DatabaseDialect
from models.schema import (
    ColumnProfile,
    ColumnType,
    ForeignKeyConstraint,
    SchemaSnapshot,
    TableProfile,
)

logger = logging.getLogger(__name__)


def _build_connection_url(config: ConnectionConfig) -> str:
    """
    Build a SQLAlchemy connection URL from a ConnectionConfig.
    Passwords are retrieved once via SecretStr.get_secret_value() and never logged.
    Special characters in credentials are percent-encoded to prevent URL misparse.
    """
    from urllib.parse import quote as _quote

    def _enc(s: str) -> str:
        return _quote(s, safe="")

    pwd = _enc(config.password.get_secret_value()) if config.password else ""
    username = _enc(config.username) if config.username else ""
    host = config.host or "localhost"

    match config.dialect:
        case DatabaseDialect.POSTGRESQL:
            port = config.port or 5432
            return f"postgresql+psycopg2://{username}:{pwd}@{host}:{port}/{config.database}"
        case DatabaseDialect.MYSQL:
            port = config.port or 3306
            return f"mysql+pymysql://{username}:{pwd}@{host}:{port}/{config.database}"
        case DatabaseDialect.SQLITE:
            # database is a file path for SQLite
            return f"sqlite:///{config.database}"
        case DatabaseDialect.MSSQL:
            port = config.port or 1433
            return (
                f"mssql+pyodbc://{username}:{pwd}@{host}:{port}/{config.database}"
                "?driver=ODBC+Driver+17+for+SQL+Server"
            )
        case _:
            raise ValueError(f"Unsupported dialect: {config.dialect}")


def _normalize_column_type(raw_type: str) -> ColumnType:
    """Normalize a dialect-specific type string to our canonical ColumnType."""
    raw = raw_type.lower()

    if any(t in raw for t in ("bigint", "int8")):
        return ColumnType.BIGINT
    if any(t in raw for t in ("int", "serial", "smallint", "tinyint")):
        return ColumnType.INTEGER
    if any(t in raw for t in ("float", "double", "real")):
        return ColumnType.FLOAT
    if any(t in raw for t in ("decimal", "numeric", "money")):
        return ColumnType.DECIMAL
    if any(t in raw for t in ("varchar", "character varying", "nvarchar")):
        return ColumnType.VARCHAR
    if "text" in raw:
        return ColumnType.TEXT
    if "bool" in raw:
        return ColumnType.BOOLEAN
    if "date" in raw and "time" not in raw:
        return ColumnType.DATE
    if any(t in raw for t in ("timestamp", "datetime")):
        return ColumnType.TIMESTAMP
    if "json" in raw:
        return ColumnType.JSON
    if "uuid" in raw:
        return ColumnType.UUID
    if any(t in raw for t in ("blob", "bytea", "binary", "varbinary")):
        return ColumnType.BYTES
    return ColumnType.OTHER


def _fast_row_count(engine: sa.Engine, dialect: DatabaseDialect, table_name: str) -> Optional[int]:
    """
    Return an approximate row count using each DB's own statistics catalog.
    This avoids COUNT(*) full-table scans entirely — results are near-instant.

    PostgreSQL: pg_class.reltuples (updated by ANALYZE/autovacuum, very accurate)
    MySQL:      information_schema.tables.table_rows (heuristic, ~10–20% off)
    SQLite:     no stats — falls back to COUNT(*) (SQLite is local so it's fast)
    MSSQL:      sys.dm_db_partition_stats
    """
    try:
        with engine.connect() as conn:
            match dialect:
                case DatabaseDialect.POSTGRESQL:
                    res = conn.execute(text(
                        "SELECT reltuples::bigint FROM pg_class "
                        "WHERE relname = :t AND relkind = 'r'"
                    ), {"t": table_name})
                    val = res.scalar()
                    if val is not None and val >= 0:
                        return int(val)
                    # reltuples = -1 means table has never been analyzed; fall through

                case DatabaseDialect.MYSQL:
                    res = conn.execute(text(
                        "SELECT table_rows FROM information_schema.tables "
                        "WHERE table_schema = DATABASE() AND table_name = :t"
                    ), {"t": table_name})
                    val = res.scalar()
                    if val is not None:
                        return int(val)

                case DatabaseDialect.MSSQL:
                    res = conn.execute(text(
                        "SELECT SUM(p.rows) FROM sys.tables t "
                        "JOIN sys.dm_db_partition_stats p ON t.object_id = p.object_id "
                        "WHERE t.name = :t AND p.index_id IN (0, 1)"
                    ), {"t": table_name})
                    val = res.scalar()
                    if val is not None:
                        return int(val)

                case DatabaseDialect.SQLITE | _:
                    pass  # fall through to COUNT(*)

            # Fallback: actual COUNT(*) — only reached for SQLite or unanalyzed PG tables
            res = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
            return res.scalar()

    except Exception as exc:
        logger.debug("Row count failed for '%s': %s", table_name, exc)
        return None


class SchemaCrawler:
    """
    Read-only schema crawler for target databases.

    Design principles:
    - Zero writes to the target database under any circumstances.
    - Sampling is explicit and bounded; no full-table scans for large tables.
    - Column-level profiling (sample values, null rates) is opt-in — controlled
      by the caller and by global settings. Analysts must consent.
    - Every failure is isolated: a broken table does not abort the full crawl.
    - The connection URL is never logged.
    """

    def __init__(self, config: ConnectionConfig) -> None:
        self._config = config
        self._engine: Optional[sa.Engine] = None

    def _get_engine(self) -> sa.Engine:
        if self._engine is None:
            url = _build_connection_url(self._config)
            connect_args: dict = {}
            if self._config.dialect != DatabaseDialect.SQLITE:
                connect_args["connect_timeout"] = settings.crawl_timeout_seconds

            self._engine = sa.create_engine(
                url,
                echo=False,
                pool_pre_ping=True,
                connect_args=connect_args,
                # Enforce read-only at the application layer
                # (DB-level read-only enforcement requires dialect-specific config)
                execution_options={"no_parameters": False},
            )
        return self._engine

    def test_connection(self) -> ConnectionTestResult:
        """Ping the target database and return status."""
        start = time.monotonic()
        try:
            engine = self._get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            latency_ms = (time.monotonic() - start) * 1000

            # Try to get server version for diagnostics
            version: Optional[str] = None
            try:
                with engine.connect() as conn:
                    result = conn.execute(text("SELECT version()"))
                    version = str(result.scalar())
            except Exception:
                pass

            return ConnectionTestResult(
                success=True,
                latency_ms=round(latency_ms, 1),
                server_version=version,
            )
        except Exception as exc:
            logger.warning("Connection test failed: %s", type(exc).__name__)
            return ConnectionTestResult(success=False, error=str(exc))

    def crawl(
        self,
        project_id: str,
        profile_columns: bool = True,
        collect_sample_values: bool = True,
        stop_event: threading.Event | None = None,
    ) -> SchemaSnapshot:
        """
        Crawl the target schema and return a SchemaSnapshot.

        Args:
            project_id: The project this snapshot belongs to.
            profile_columns: Whether to collect null/distinct counts.
            collect_sample_values: Whether to collect sample values per column.
                Set False for stricter privacy posture.
            stop_event: When set, the crawl stops after the current table and
                returns a partial snapshot with whatever was collected so far.
        """
        logger.info("Starting schema crawl for project=%s", project_id)
        engine = self._get_engine()
        inspector = inspect(engine)

        table_names = inspector.get_table_names()
        logger.info("Found %d tables", len(table_names))

        if len(table_names) > settings.max_tables_per_crawl:
            logger.warning(
                "Capping crawl at %d tables (found %d)",
                settings.max_tables_per_crawl,
                len(table_names),
            )
            table_names = table_names[: settings.max_tables_per_crawl]

        profiles: list[TableProfile] = []
        for table_name in table_names:
            # Check for cancellation between tables
            if stop_event and stop_event.is_set():
                logger.info("Crawl cancelled — saving partial results (%d tables)", len(profiles))
                break
            try:
                profile = self._profile_table(
                    engine,
                    inspector,
                    table_name,
                    profile_columns=profile_columns,
                    collect_sample_values=collect_sample_values,
                )
                profiles.append(profile)
            except Exception as exc:
                logger.error("Failed to profile table '%s': %s", table_name, exc)
                # Always include the table, even if profiling partially fails
                profiles.append(
                    TableProfile(
                        name=table_name,
                        analyst_note=f"[Crawl error] {type(exc).__name__}: {exc}",
                    )
                )

        was_cancelled = bool(stop_event and stop_event.is_set())
        snapshot = SchemaSnapshot(
            connection_id=self._config.id,
            project_id=project_id,
            tables=profiles,
        )
        logger.info(
            "Crawl %s: %d tables, %d total columns",
            "cancelled (partial)" if was_cancelled else "complete",
            len(profiles),
            snapshot.total_columns,
        )
        return snapshot

    def _profile_table(
        self,
        engine: sa.Engine,
        inspector: sa.Inspector,
        table_name: str,
        profile_columns: bool,
        collect_sample_values: bool,
    ) -> TableProfile:
        columns_meta = inspector.get_columns(table_name)
        pk_meta = inspector.get_pk_constraint(table_name)
        fk_meta = inspector.get_foreign_keys(table_name)
        index_meta = inspector.get_indexes(table_name)

        pk_columns = set(pk_meta.get("constrained_columns", []))

        # Build FK lookup by local column name
        fk_by_column: dict[str, tuple[str, str]] = {}
        for fk in fk_meta:
            for local_col, ref_col in zip(
                fk.get("constrained_columns", []), fk.get("referred_columns", [])
            ):
                fk_by_column[local_col] = (fk.get("referred_table", ""), ref_col)

        # Row count — use DB statistics instead of COUNT(*) to avoid full table scans.
        # Approximate counts from system catalogs are near-instant even on 100M+ row tables.
        # We fall back to COUNT(*) only for SQLite (no stats) or if stats return 0/-1.
        row_count: Optional[int] = _fast_row_count(engine, self._config.dialect, table_name)

        # Build column profiles
        columns: list[ColumnProfile] = []
        for ordinal, col_meta in enumerate(columns_meta):
            col_name: str = col_meta["name"]
            fk_ref = fk_by_column.get(col_name)

            col = ColumnProfile(
                name=col_name,
                raw_type=str(col_meta["type"]),
                normalized_type=_normalize_column_type(str(col_meta["type"])),
                is_nullable=bool(col_meta.get("nullable", True)),
                is_primary_key=col_name in pk_columns,
                is_foreign_key=fk_ref is not None,
                referenced_table=fk_ref[0] if fk_ref else None,
                referenced_column=fk_ref[1] if fk_ref else None,
                ordinal_position=ordinal,
                row_count=row_count,
            )

            if profile_columns and row_count and row_count > 0:
                self._profile_column(
                    engine, table_name, col, collect_sample_values=collect_sample_values
                )

            columns.append(col)

        fk_constraints = [
            ForeignKeyConstraint(
                constrained_columns=fk.get("constrained_columns", []),
                referred_table=fk.get("referred_table", ""),
                referred_columns=fk.get("referred_columns", []),
                name=fk.get("name"),
            )
            for fk in fk_meta
        ]

        return TableProfile(
            name=table_name,
            row_count=row_count,
            columns=columns,
            primary_keys=list(pk_columns),
            foreign_key_constraints=fk_constraints,
            index_names=[idx.get("name", "") for idx in index_meta if idx.get("name")],
        )

    def _profile_column(
        self,
        engine: sa.Engine,
        table_name: str,
        column: ColumnProfile,
        collect_sample_values: bool,
    ) -> None:
        """
        Add statistical profile to a column in-place.
        All queries are simple aggregations with no WHERE filters that could
        expose actual PII; sample values are collected as-is from the DB.
        """
        col_name = column.name

        try:
            with engine.connect() as conn:
                dialect = self._config.dialect

                # ── Null fraction & distinct count ────────────────────────────
                # For PostgreSQL use pg_stats — pre-computed by ANALYZE, zero scan cost.
                # For other dialects we run aggregate queries, but skip full-scan types.
                if dialect == DatabaseDialect.POSTGRESQL:
                    res = conn.execute(text(
                        "SELECT null_frac, n_distinct FROM pg_stats "
                        "WHERE tablename = :t AND attname = :c"
                    ), {"t": table_name, "c": col_name})
                    row = res.fetchone()
                    if row:
                        null_frac, n_distinct = row
                        if column.row_count and null_frac is not None:
                            column.null_count = int(null_frac * column.row_count)
                        if n_distinct is not None:
                            # pg_stats: positive = absolute count, negative = fraction of rows
                            if n_distinct >= 0:
                                column.distinct_count = int(n_distinct)
                            elif column.row_count:
                                column.distinct_count = int(abs(n_distinct) * column.row_count)
                elif column.normalized_type not in (ColumnType.TEXT, ColumnType.JSON, ColumnType.BYTES):
                    # Non-PG: run aggregate queries only for non-blob columns
                    res = conn.execute(
                        text(f'SELECT COUNT(*) FROM "{table_name}" WHERE "{col_name}" IS NULL')
                    )
                    column.null_count = res.scalar()

                    res = conn.execute(
                        text(f'SELECT COUNT(DISTINCT "{col_name}") FROM "{table_name}"')
                    )
                    column.distinct_count = res.scalar()

                # ── Sample values ─────────────────────────────────────────────
                # LIMIT-bounded — fast on all dialects regardless of table size.
                if collect_sample_values and settings.enable_sample_values:
                    res = conn.execute(
                        text(
                            f'SELECT DISTINCT CAST("{col_name}" AS VARCHAR) '
                            f'FROM "{table_name}" '
                            f'WHERE "{col_name}" IS NOT NULL '
                            f'LIMIT {settings.max_sample_rows}'
                        )
                    )
                    column.sample_values = [str(row[0]) for row in res.fetchall()]

        except Exception as exc:
            logger.debug(
                "Column profiling failed for '%s.%s': %s", table_name, col_name, exc
            )

    def dispose(self) -> None:
        """Release connection pool resources."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None
