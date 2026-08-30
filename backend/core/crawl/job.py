from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from db.orm_models import CrawlJobORM, CrawlTaskORM

logger = logging.getLogger(__name__)

# Crawl stages, in execution order.
STAGE_CATALOG = "catalog"
STAGE_CHEAP_STATS = "cheap_stats"
STAGE_SAMPLED_PROFILING = "sampled_profiling"
STAGE_SAMPLE_VALUES = "sample_values"

ALL_STAGES = [STAGE_CATALOG, STAGE_CHEAP_STATS, STAGE_SAMPLED_PROFILING, STAGE_SAMPLE_VALUES]


class CrawlJobService:
    """
    Persistence for staged, resumable crawls.

    Replaces the previous module-level `_crawl_cancel_events: dict` +
    `threading.Lock` in api/projects.py, which (a) lived only in one worker
    process's memory, so DELETE /crawl landing on a different worker than
    the one running the crawl would silently do nothing, and (b) had no
    record of progress or partial completion — an interrupted crawl always
    restarted from table 1.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_job(self, project_id: str, mode: str, table_names: list[str]) -> CrawlJobORM:
        job = CrawlJobORM(
            id=str(uuid.uuid4()),
            project_id=project_id,
            status="pending",
            mode=mode,
        )
        self._db.add(job)
        self._db.flush()

        for table_name in table_names:
            for stage in ALL_STAGES:
                self._db.add(
                    CrawlTaskORM(
                        id=str(uuid.uuid4()),
                        job_id=job.id,
                        table_name=table_name,
                        stage=stage,
                        status="pending",
                    )
                )
        self._db.commit()
        self._db.refresh(job)
        return job

    def get_job(self, job_id: str) -> CrawlJobORM | None:
        return self._db.get(CrawlJobORM, job_id)

    def mark_running(self, job_id: str, stage: str) -> None:
        job = self._db.get(CrawlJobORM, job_id)
        if job:
            job.status = "running"
            job.current_stage = stage
            job.updated_at = datetime.utcnow()
            self._db.commit()

    def mark_completed(self, job_id: str, snapshot_id: str) -> None:
        job = self._db.get(CrawlJobORM, job_id)
        if job:
            job.status = "completed"
            job.snapshot_id = snapshot_id
            job.finished_at = datetime.utcnow()
            job.updated_at = job.finished_at
            self._db.commit()

    def mark_cancelled(self, job_id: str) -> None:
        job = self._db.get(CrawlJobORM, job_id)
        if job:
            job.status = "cancelled"
            job.finished_at = datetime.utcnow()
            job.updated_at = job.finished_at
            self._db.commit()

    def mark_failed(self, job_id: str, error: str) -> None:
        job = self._db.get(CrawlJobORM, job_id)
        if job:
            job.status = "failed"
            job.error = error
            job.finished_at = datetime.utcnow()
            job.updated_at = job.finished_at
            self._db.commit()

    def request_cancel(self, job_id: str) -> bool:
        """Returns True if a job was found and flagged (regardless of whether
        it was actually running — matches the old endpoint's 204-always
        behavior, but now the flag is durable and worker-agnostic)."""
        job = self._db.get(CrawlJobORM, job_id)
        if not job:
            return False
        job.cancel_requested = True
        self._db.commit()
        return True

    def is_cancel_requested(self, job_id: str) -> bool:
        job = self._db.get(CrawlJobORM, job_id)
        return bool(job and job.cancel_requested)

    def get_latest_job(self, project_id: str) -> CrawlJobORM | None:
        return (
            self._db.query(CrawlJobORM)
            .filter(CrawlJobORM.project_id == project_id)
            .order_by(CrawlJobORM.created_at.desc())
            .first()
        )

    def pending_tables_for_stage(self, job_id: str, stage: str) -> list[str]:
        """Tables not yet done for this stage — the resume set. On a fresh
        job this is all tables; on a resumed job it's whatever the previous
        run didn't finish."""
        rows = (
            self._db.query(CrawlTaskORM)
            .filter(
                CrawlTaskORM.job_id == job_id,
                CrawlTaskORM.stage == stage,
                CrawlTaskORM.status == "pending",
            )
            .all()
        )
        return [r.table_name for r in rows]

    def mark_task(self, job_id: str, table_name: str, stage: str, status: str, error: str | None = None) -> None:
        task = (
            self._db.query(CrawlTaskORM)
            .filter(
                CrawlTaskORM.job_id == job_id,
                CrawlTaskORM.table_name == table_name,
                CrawlTaskORM.stage == stage,
            )
            .first()
        )
        if task:
            task.status = status
            task.error = error
            task.updated_at = datetime.utcnow()
            self._db.commit()

    def progress(self, job_id: str) -> dict:
        job = self._db.get(CrawlJobORM, job_id)
        if not job:
            return {}

        stage_progress = {}
        for stage in ALL_STAGES:
            total = (
                self._db.query(CrawlTaskORM)
                .filter(CrawlTaskORM.job_id == job_id, CrawlTaskORM.stage == stage)
                .count()
            )
            done = (
                self._db.query(CrawlTaskORM)
                .filter(
                    CrawlTaskORM.job_id == job_id,
                    CrawlTaskORM.stage == stage,
                    CrawlTaskORM.status.in_(["done", "skipped", "failed"]),
                )
                .count()
            )
            stage_progress[stage] = {"done": done, "total": total}

        return {
            "job_id": job.id,
            "status": job.status,
            "current_stage": job.current_stage,
            "mode": job.mode,
            "error": job.error,
            "snapshot_id": job.snapshot_id,
            "stages": stage_progress,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        }
