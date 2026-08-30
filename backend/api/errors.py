from __future__ import annotations

from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel


class APIError(BaseModel):
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None


def not_found(entity: str, entity_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=f"{entity} '{entity_id}' not found",
    )


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def server_error(message: str) -> HTTPException:
    return HTTPException(status_code=500, detail=message)


def no_snapshot() -> HTTPException:
    """Shared 404 for 'no schema snapshot exists yet' — previously this
    message was hand-typed with slightly different wording at each of five
    call sites across inference.py/datasets.py/projects.py."""
    return HTTPException(status_code=404, detail="No schema snapshot found. Run a crawl first.")
