from __future__ import annotations

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, SecretStr, field_validator


class DatabaseDialect(str, Enum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    MSSQL = "mssql"
    DUCKDB = "duckdb"


class ConnectionConfig(BaseModel):
    """
    A database connection configuration.

    Passwords are stored as SecretStr to prevent accidental logging.
    They are never serialized to JSON in plain text.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=128)
    dialect: DatabaseDialect
    host: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    database: str = Field(..., min_length=1)
    username: Optional[str] = None
    password: Optional[SecretStr] = None
    ssl_mode: Optional[str] = None
    extra_params: dict[str, str] = Field(default_factory=dict)

    @field_validator("host", mode="before")
    @classmethod
    def strip_host(cls, v: Optional[str]) -> Optional[str]:
        return v.strip() if v else v

    def get_display_name(self) -> str:
        if self.host:
            return f"{self.dialect.value}://{self.host}/{self.database}"
        return f"{self.dialect.value}:///{self.database}"

    model_config = {"json_encoders": {SecretStr: lambda _: "***"}}


class ConnectionTestResult(BaseModel):
    success: bool
    latency_ms: Optional[float] = None
    server_version: Optional[str] = None
    error: Optional[str] = None


class ConnectionSummary(BaseModel):
    """Safe-to-expose connection info (no password)."""

    id: str
    name: str
    dialect: DatabaseDialect
    display_name: str
