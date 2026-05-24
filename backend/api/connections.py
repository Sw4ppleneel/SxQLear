from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.errors import bad_request, not_found
from core.memory.project_memory import ProjectMemoryService
from core.schema.crawler import SchemaCrawler
from core.schema.airtable_crawler import AirtableCrawler
from db.session import get_db
from models.connection import (
    AirtableConnectionConfig,
    ConnectionConfig,
    ConnectionSummary,
    ConnectionTestResult,
    DatabaseDialect,
)
from models.schema import SchemaSnapshot

router = APIRouter(prefix="/connections", tags=["connections"])


class CreateConnectionRequest(BaseModel):
    name: str
    dialect: DatabaseDialect
    host: Optional[str] = None
    port: Optional[int] = None
    database: str
    username: Optional[str] = None
    password: Optional[str] = None
    ssl_mode: Optional[str] = None


class CreateAirtableConnectionRequest(BaseModel):
    name: str
    api_key: str
    base_id: str


@router.post("/test", response_model=ConnectionTestResult)
def test_connection(req: CreateConnectionRequest) -> ConnectionTestResult:
    """
    Test a database connection without saving it.
    Use this before creating a project to verify credentials.
    """
    from pydantic import SecretStr

    config = ConnectionConfig(
        name=req.name,
        dialect=req.dialect,
        host=req.host,
        port=req.port,
        database=req.database,
        username=req.username,
        password=SecretStr(req.password) if req.password else None,
        ssl_mode=req.ssl_mode,
    )

    start = time.monotonic()
    crawler = SchemaCrawler(config)
    result = crawler.test_connection()
    crawler.dispose()
    return result


@router.post("/airtable/test", response_model=ConnectionTestResult)
def test_airtable_connection(req: CreateAirtableConnectionRequest) -> ConnectionTestResult:
    from pydantic import SecretStr

    config = AirtableConnectionConfig(
        name=req.name,
        api_key=SecretStr(req.api_key),
        base_id=req.base_id,
    )

    crawler = AirtableCrawler(config)
    result = crawler.test_connection()
    crawler.dispose()
    return result


@router.post("/airtable/crawl", response_model=SchemaSnapshot)
def crawl_airtable(
    req: CreateAirtableConnectionRequest,
    project_id: str,
    db: Session = Depends(get_db),
) -> SchemaSnapshot:
    from pydantic import SecretStr

    service = ProjectMemoryService(db)
    project = service.get_project(project_id)
    if not project:
        raise not_found("Project", project_id)

    config = AirtableConnectionConfig(
        name=req.name,
        api_key=SecretStr(req.api_key),
        base_id=req.base_id,
    )

    crawler = AirtableCrawler(config)
    try:
        snapshot = crawler.crawl(project_id=project_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Airtable crawl failed: {exc}")
    finally:
        crawler.dispose()

    service.save_snapshot(snapshot)
    return snapshot
