from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.errors import bad_request, not_found
from core.memory.project_memory import ProjectMemoryService
from core.schema.crawler import SchemaCrawler
from db.session import get_db
from models.connection import (
    ConnectionConfig,
    ConnectionSummary,
    ConnectionTestResult,
    DatabaseDialect,
)

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
