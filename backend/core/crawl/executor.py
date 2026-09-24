from __future__ import annotations

import logging

import sqlalchemy as sa

from config import settings
from core.crawl.catalog import catalog_all_tables
from core.crawl.job import (
    ALL_STAGES,
    STAGE_CATALOG,
    STAGE_CHEAP_STATS,
    STAGE_SAMPLED_PROFILING,
    STAGE_SAMPLE_VALUES,
    CrawlJobService,
)
from core.memory.project_memory import ProjectMemoryService
from core.schema.crawler import SchemaCrawler, _fast_row_count, _build_connection_url
from db.session import SessionLocal
from models.connection import ConnectionConfig, DatabaseDialect
from models.schema import SchemaSnapshot

logger = logging.getLogger(__name__)


def _index_for_search(memory_service: ProjectMemoryService, snapshot: SchemaSnapshot) -> None:
    try:
        memory_service.index_snapshot_for_search(snapshot)
    except Exception:
        logger.exception("Column search indexing failed for snapshot %s", snapshot.id)


def run_crawl_job(job_id: str, project_id: str, config: ConnectionConfig, mode: str) -> None:
    """
    The staged crawl worker. Invoked via FastAPI BackgroundTasks (runs in a
    thread pool after the 202 response is already sent — the request path
    used to block for the entire crawl duration; it no longer does).

    Uses its own DB session rather than the request's, since it runs after
    the request that created the job has already returned.

    Stages, each checkpointed per-table in crawl_tasks so a job that's
    interrupted (process restart, crash) resumes from wherever it left off
    instead of starting over:
      A. catalog          — batched reflection, all tables, seconds
      B. cheap_stats      — row counts via catalog statistics, no scans
      C/D. profiling      — per-column null/distinct/sample-values (full mode only)

    C and D are tracked as separate task rows (matching the plan's 4-stage
    design) but currently execute together in one pass, since the existing
    per-column profiling query computes both in a single round trip; each
    table's C and D tasks are marked done together for that reason.
    """
    db = SessionLocal()
    try:
        job_service = CrawlJobService(db)
        memory_service = ProjectMemoryService(db)

        if config.dialect == DatabaseDialect.AIRTABLE:
            _run_airtable_job(job_service, memory_service, job_id, project_id, config)
            return

        engine = sa.create_engine(
            _build_connection_url(config),
            pool_pre_ping=True,
            connect_args=(
                {"connect_timeout": settings.crawl_timeout_seconds}
                if config.dialect != DatabaseDialect.SQLITE
                else {}
            ),
        )
        try:
            _run_sql_job(job_service, memory_service, engine, config, job_id, project_id, mode)
        finally:
            engine.dispose()

    except Exception as exc:
        logger.exception("Crawl job %s failed", job_id)
        job_service = CrawlJobService(db)
        job_service.mark_failed(job_id, f"{type(exc).__name__}: {exc}")
    finally:
        db.close()


def _run_sql_job(
    job_service: CrawlJobService,
    memory_service: ProjectMemoryService,
    engine: sa.Engine,
    config: ConnectionConfig,
    job_id: str,
    project_id: str,
    mode: str,
) -> None:
    # ── Stage A: catalog ──────────────────────────────────────────────────
    job_service.mark_running(job_id, STAGE_CATALOG)
    table_profiles = catalog_all_tables(engine)
    table_map = {t.name: t for t in table_profiles}

    for name in table_map:
        job_service.mark_task(job_id, name, STAGE_CATALOG, "done")

    snapshot = SchemaSnapshot(
        connection_id=config.id, project_id=project_id, tables=list(table_map.values())
    )
    memory_service.save_snapshot(snapshot)

    if job_service.is_cancel_requested(job_id):
        job_service.mark_cancelled(job_id)
        return

    # ── Stage B: cheap stats (row counts, no table scans) ────────────────
    # Runs in BOTH modes — "quick" means "skip the expensive per-column
    # profiling in stage C/D", not "skip row counts too". Row counts come
    # from catalog statistics (no table scans), so they're cheap enough to
    # always include; without this, quick mode wouldn't deliver what its own
    # docstring promises ("catalog + row counts only").
    job_service.mark_running(job_id, STAGE_CHEAP_STATS)
    for table_name in job_service.pending_tables_for_stage(job_id, STAGE_CHEAP_STATS):
        if job_service.is_cancel_requested(job_id):
            break
        table = table_map.get(table_name)
        if table is None:
            job_service.mark_task(job_id, table_name, STAGE_CHEAP_STATS, "skipped")
            continue
        try:
            row_count = _fast_row_count(engine, config.dialect, table_name)
            table.row_count = row_count
            for col in table.columns:
                col.row_count = row_count
            job_service.mark_task(job_id, table_name, STAGE_CHEAP_STATS, "done")
        except Exception as exc:
            logger.warning("Stage B failed for '%s': %s", table_name, exc)
            job_service.mark_task(job_id, table_name, STAGE_CHEAP_STATS, "failed", str(exc))

    snapshot = SchemaSnapshot(
        connection_id=config.id,
        project_id=project_id,
        tables=list(table_map.values()),
        version=snapshot.version + 1,
    )
    memory_service.save_snapshot(snapshot)

    if job_service.is_cancel_requested(job_id):
        job_service.mark_cancelled(job_id)
        return

    if mode == "quick":
        _index_for_search(memory_service, snapshot)
        job_service.mark_completed(job_id, snapshot.id)
        return

    # ── Stage C/D: per-column profiling + sample values ───────────────────
    job_service.mark_running(job_id, STAGE_SAMPLED_PROFILING)
    crawler = SchemaCrawler(config)
    for table_name in job_service.pending_tables_for_stage(job_id, STAGE_SAMPLED_PROFILING):
        if job_service.is_cancel_requested(job_id):
            break
        table = table_map.get(table_name)
        if table is None:
            job_service.mark_task(job_id, table_name, STAGE_SAMPLED_PROFILING, "skipped")
            job_service.mark_task(job_id, table_name, STAGE_SAMPLE_VALUES, "skipped")
            continue
        try:
            if table.row_count and table.row_count > 0:
                for col in table.columns:
                    crawler._profile_column(
                        engine, table_name, col,
                        collect_sample_values=settings.enable_sample_values,
                    )
            job_service.mark_task(job_id, table_name, STAGE_SAMPLED_PROFILING, "done")
            job_service.mark_task(job_id, table_name, STAGE_SAMPLE_VALUES, "done")
        except Exception as exc:
            logger.warning("Stage C/D failed for '%s': %s", table_name, exc)
            job_service.mark_task(job_id, table_name, STAGE_SAMPLED_PROFILING, "failed", str(exc))
            job_service.mark_task(job_id, table_name, STAGE_SAMPLE_VALUES, "failed", str(exc))

    was_cancelled = job_service.is_cancel_requested(job_id)
    snapshot = SchemaSnapshot(
        connection_id=config.id,
        project_id=project_id,
        tables=list(table_map.values()),
        version=snapshot.version + 1,
    )
    memory_service.save_snapshot(snapshot)

    _index_for_search(memory_service, snapshot)

    if was_cancelled:
        job_service.mark_cancelled(job_id)
    else:
        job_service.mark_completed(job_id, snapshot.id)


def _run_airtable_job(
    job_service: CrawlJobService,
    memory_service: ProjectMemoryService,
    job_id: str,
    project_id: str,
    config: ConnectionConfig,
) -> None:
    """
    Airtable has no batched-reflection equivalent to SQLAlchemy's
    get_multi_columns() — its schema API returns everything in one response
    already — so there is no separate catalog/profiling split to stage here.
    All task rows are marked done together after the single crawl call.
    """
    from pydantic import SecretStr

    from core.schema.airtable_crawler import AirtableCrawler
    from models.connection import AirtableConnectionConfig

    job_service.mark_running(job_id, STAGE_CATALOG)

    if not config.password:
        job_service.mark_failed(job_id, "Airtable API key missing")
        return

    crawler = AirtableCrawler(
        AirtableConnectionConfig(
            name=config.name,
            api_key=SecretStr(config.password.get_secret_value()),
            base_id=config.database,
        )
    )
    try:
        snapshot_raw = crawler.crawl(project_id=project_id)
    except Exception as exc:
        job_service.mark_failed(job_id, f"Airtable crawl failed: {exc}")
        return
    finally:
        crawler.dispose()

    for table in snapshot_raw.tables:
        for stage in ALL_STAGES:
            job_service.mark_task(job_id, table.name, stage, "done")

    memory_service.save_snapshot(snapshot_raw)
    _index_for_search(memory_service, snapshot_raw)
    job_service.mark_completed(job_id, snapshot_raw.id)
