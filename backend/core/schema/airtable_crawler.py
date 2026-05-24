from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from models.connection import AirtableConnectionConfig, ConnectionTestResult
from models.schema import ColumnProfile, ColumnType, SchemaSnapshot, TableProfile

logger = logging.getLogger(__name__)


_AIRTABLE_TYPE_MAP: dict[str, ColumnType] = {
    "singleLineText": ColumnType.VARCHAR,
    "multilineText": ColumnType.TEXT,
    "richText": ColumnType.TEXT,
    "number": ColumnType.FLOAT,
    "percent": ColumnType.FLOAT,
    "currency": ColumnType.DECIMAL,
    "autoNumber": ColumnType.INTEGER,
    "count": ColumnType.INTEGER,
    "checkbox": ColumnType.BOOLEAN,
    "date": ColumnType.DATE,
    "dateTime": ColumnType.TIMESTAMP,
    "multipleRecordLinks": ColumnType.OTHER,
    "formula": ColumnType.OTHER,
    "rollup": ColumnType.OTHER,
    "lookup": ColumnType.OTHER,
    "email": ColumnType.VARCHAR,
    "url": ColumnType.VARCHAR,
    "phoneNumber": ColumnType.VARCHAR,
    "singleSelect": ColumnType.VARCHAR,
    "multipleSelects": ColumnType.TEXT,
    "createdTime": ColumnType.TIMESTAMP,
    "lastModifiedTime": ColumnType.TIMESTAMP,
    "attachment": ColumnType.BYTES,
}


class AirtableCrawler:
    def __init__(self, config: AirtableConnectionConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url="https://api.airtable.com/v0",
            headers={
                "Authorization": f"Bearer {config.api_key.get_secret_value()}",
            },
            timeout=30.0,
        )

    def test_connection(self) -> ConnectionTestResult:
        start = time.monotonic()
        try:
            response = self._client.get(f"/meta/bases/{self._config.base_id}/tables")
            response.raise_for_status()
            latency_ms = (time.monotonic() - start) * 1000
            return ConnectionTestResult(
                success=True,
                latency_ms=latency_ms,
                server_version="Airtable API v0",
            )
        except Exception as exc:
            return ConnectionTestResult(success=False, error=str(exc))

    def crawl(
        self,
        project_id: str,
        profile_columns: bool = True,
        collect_sample_values: bool = True,
        stop_event=None,
    ) -> SchemaSnapshot:
        try:
            schema_response = self._client.get(
                f"/meta/bases/{self._config.base_id}/tables"
            )
            schema_response.raise_for_status()
            tables_payload = schema_response.json()
            tables = tables_payload.get("tables", [])
        except Exception as exc:
            raise RuntimeError(f"Failed to fetch Airtable schema: {exc}")

        table_id_to_name = {table.get("id"): table.get("name") for table in tables}
        profiles: list[TableProfile] = []

        for table in tables:
            if stop_event and stop_event.is_set():
                logger.info("Airtable crawl cancelled — saving partial results (%d tables)", len(profiles))
                break

            table_id = table.get("id")
            table_name = table.get("name", "unknown")

            try:
                fields = table.get("fields", [])
                columns: list[ColumnProfile] = []
                samples_by_field: dict[str, list[str]] = {field.get("name", ""): [] for field in fields}

                if collect_sample_values:
                    records_response = self._client.get(
                        f"/{self._config.base_id}/{table_id}",
                        params={"maxRecords": 10},
                    )
                    records_response.raise_for_status()
                    records_payload = records_response.json()
                    records = records_payload.get("records", [])

                    for record in records:
                        fields_data = record.get("fields", {})
                        for field_name, value in fields_data.items():
                            if value is None:
                                continue
                            samples = samples_by_field.setdefault(field_name, [])
                            if len(samples) < 10:
                                samples.append(str(value))

                for ordinal, field in enumerate(fields):
                    field_name = field.get("name", "unknown")
                    field_type = field.get("type", "unknown")
                    normalized_type = _AIRTABLE_TYPE_MAP.get(field_type, ColumnType.OTHER)

                    is_foreign_key = field_type == "multipleRecordLinks"
                    referenced_table = None
                    if is_foreign_key:
                        options = field.get("options") or {}
                        referenced_table = options.get("linkedTableId")

                    column = ColumnProfile(
                        name=field_name,
                        raw_type=field_type,
                        normalized_type=normalized_type,
                        is_nullable=True,
                        is_primary_key=False,
                        is_foreign_key=is_foreign_key,
                        referenced_table=referenced_table,
                        referenced_column=None,
                        has_index=False,
                        ordinal_position=ordinal,
                        row_count=None,
                        null_count=None,
                        distinct_count=None,
                        sample_values=samples_by_field.get(field_name, [])[:10],
                    )
                    columns.append(column)

                profiles.append(
                    TableProfile(
                        name=table_name,
                        row_count=None,
                        columns=columns,
                        primary_keys=[],
                        foreign_key_constraints=[],
                        index_names=[],
                    )
                )
            except Exception as exc:
                logger.exception("Airtable crawl failed for table '%s': %s", table_name, exc)
                profiles.append(
                    TableProfile(
                        name=table_name,
                        row_count=None,
                        columns=[],
                        primary_keys=[],
                        foreign_key_constraints=[],
                        index_names=[],
                        analyst_note=f"[Crawl error] {exc}",
                    )
                )

        for profile in profiles:
            for column in profile.columns:
                if column.is_foreign_key and column.referenced_table:
                    resolved = table_id_to_name.get(column.referenced_table)
                    if resolved:
                        column.referenced_table = resolved

        return SchemaSnapshot(
            connection_id=self._config.id,
            project_id=project_id,
            tables=profiles,
        )

    def dispose(self) -> None:
        self._client.close()
