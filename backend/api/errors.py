from __future__ import annotations

import time

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional


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
