from __future__ import annotations

import re
import threading
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.errors import bad_request, not_found
from core.memory.project_memory import ProjectMemoryService
from core.schema.crawler import SchemaCrawler
from core.schema.graph import SchemaGraph
from db.session import get_db
from models.connection import ConnectionConfig, DatabaseDialect
from models.memory import Project
from models.schema import SchemaSnapshot, TableProfile

router = APIRouter(prefix="/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str
    description: Optional[str] = None
    # Connection details — stored securely in project memory
    dialect: DatabaseDialect
    host: Optional[str] = None
    port: Optional[int] = None
    database: str
    username: Optional[str] = None
    password: Optional[str] = None
    ssl_mode: Optional[str] = None


@router.post("", response_model=Project, status_code=201)
def create_project(req: CreateProjectRequest, db: Session = Depends(get_db)) -> Project:
    """Create a new project. The connection config is stored in local project memory."""
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

    # Store config as JSON — password is masked in the serialized form
    config_dict = config.model_dump(mode="json")
    if req.password:
        config_dict["password"] = req.password  # Store for re-use; only in local SQLite

    service = ProjectMemoryService(db)
    return service.create_project(
        name=req.name,
        connection_config=config_dict,
        description=req.description,
    )


@router.get("", response_model=list[Project])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    service = ProjectMemoryService(db)
    return service.list_projects()


@router.get("/{project_id}", response_model=Project)
def get_project(project_id: str, db: Session = Depends(get_db)) -> Project:
    service = ProjectMemoryService(db)
    project = service.get_project(project_id)
    if not project:
        raise not_found("Project", project_id)
    return project


@router.get("/{project_id}/connection")
def get_project_connection(project_id: str, db: Session = Depends(get_db)) -> dict:
    """Return the stored connection config for a project (password omitted)."""
    service = ProjectMemoryService(db)
    config = service.get_connection_config(project_id)
    if not config:
        raise not_found("Project", project_id)
    return {k: v for k, v in config.items() if k != "password"}


class UpdateProjectRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    dialect: Optional[DatabaseDialect] = None
    host: Optional[str] = None
    port: Optional[int] = None
    database: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None  # None / empty = keep existing password
    ssl_mode: Optional[str] = None


@router.put("/{project_id}", response_model=Project)
def update_project(
    project_id: str, req: UpdateProjectRequest, db: Session = Depends(get_db)
) -> Project:
    """Update project name, description, and/or connection credentials."""
    service = ProjectMemoryService(db)
    project = service.get_project(project_id)
    if not project:
        raise not_found("Project", project_id)

    existing_config = service.get_connection_config(project_id)
    if not existing_config:
        raise bad_request("Project has no connection config")

    # Merge — only overwrite fields that were explicitly provided
    new_config = dict(existing_config)
    for field in ("dialect", "host", "port", "database", "username", "ssl_mode"):
        val = getattr(req, field, None)
        if val is not None:
            new_config[field] = val
    if req.name is not None:
        new_config["name"] = req.name
    if req.password:  # Only replace if non-empty string supplied
        new_config["password"] = req.password

    from db.repositories.project_repo import ProjectRepository
    repo = ProjectRepository(db)
    updates: dict = {"connection_config_json": new_config}
    if req.name is not None:
        updates["name"] = req.name
    if req.description is not None:
        updates["description"] = req.description

    if not repo.update_project(project_id, **updates):
        raise not_found("Project", project_id)

    return service.get_project(project_id)


@router.delete("/{project_id}", status_code=204)
def delete_project(project_id: str, db: Session = Depends(get_db)):
    service = ProjectMemoryService(db)
    from db.repositories.project_repo import ProjectRepository
    repo = ProjectRepository(db)
    if not repo.delete_project(project_id):
        raise not_found("Project", project_id)
    return Response(status_code=204)


# ── Schema crawling ───────────────────────────────────────────────────────────

# In-memory cancel events: project_id → threading.Event
# When set, the running crawl for that project stops after the current table.
_crawl_cancel_events: dict[str, threading.Event] = {}
_crawl_lock = threading.Lock()


class CrawlOptions(BaseModel):
    mode: Literal["full", "quick"] = "full"
    """
    full  — full column profiling (null/distinct counts, sample values) + inference
    quick — table names, column headers, and row counts only; still runs inference
    """


@router.post("/{project_id}/crawl", response_model=SchemaSnapshot)
def crawl_schema(
    project_id: str,
    options: Optional[CrawlOptions] = None,
    db: Session = Depends(get_db),
) -> SchemaSnapshot:
    """
    Crawl the target database and store a new SchemaSnapshot.

    mode=full  — full column profiling (null/distinct counts, sample values)
    mode=quick — table names, column headers, and row counts only (fast)

    Both modes save the snapshot. A running crawl can be stopped via
    DELETE /projects/{project_id}/crawl which saves partial results.
    """
    opts = options or CrawlOptions()
    service = ProjectMemoryService(db)

    project = service.get_project(project_id)
    if not project:
        raise not_found("Project", project_id)

    config_dict = service.get_connection_config(project_id)
    if not config_dict:
        raise bad_request("Project has no connection config")

    # Translate mode → profiling flags
    profile_columns = opts.mode == "full"
    collect_sample_values = opts.mode == "full"

    # Register a cancel event so DELETE /crawl can stop us between tables
    cancel_event = threading.Event()
    with _crawl_lock:
        _crawl_cancel_events[project_id] = cancel_event

    config = _deserialize_connection_config(config_dict)
    if config.dialect == DatabaseDialect.AIRTABLE:
        from pydantic import SecretStr
        from core.schema.airtable_crawler import AirtableCrawler
        from models.connection import AirtableConnectionConfig

        if not config.password:
            raise HTTPException(status_code=400, detail="Airtable API key missing")

        crawler = AirtableCrawler(
            AirtableConnectionConfig(
                name=project.name,
                api_key=SecretStr(config.password.get_secret_value()),
                base_id=config.database,
            )
        )
    else:
        crawler = SchemaCrawler(config)

    try:
        snapshot = crawler.crawl(
            project_id=project_id,
            profile_columns=profile_columns,
            collect_sample_values=collect_sample_values,
            stop_event=cancel_event,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Schema crawl failed: {exc}")
    finally:
        with _crawl_lock:
            _crawl_cancel_events.pop(project_id, None)
    crawler.dispose()

    service.save_snapshot(snapshot)
    return snapshot


@router.delete("/{project_id}/crawl", status_code=204)
def cancel_crawl(project_id: str):
    """
    Signal a running crawl to stop. The crawl will finish its current table
    and then save a partial snapshot. Returns 204 regardless of whether
    a crawl was running.
    """
    with _crawl_lock:
        event = _crawl_cancel_events.get(project_id)
    if event:
        event.set()
    return Response(status_code=204)



@router.get("/{project_id}/snapshots/latest", response_model=SchemaSnapshot)
def get_latest_snapshot(project_id: str, db: Session = Depends(get_db)) -> SchemaSnapshot:
    service = ProjectMemoryService(db)
    snapshot = service.get_latest_snapshot(project_id)
    if not snapshot:
        raise HTTPException(
            status_code=404,
            detail="No snapshot found for this project. Run a crawl first.",
        )
    return snapshot


@router.get("/{project_id}/graph")
def get_schema_graph(project_id: str, db: Session = Depends(get_db)) -> dict:
    """
    Returns the schema graph in React Flow format (nodes + edges).
    Includes relationship validation status from project memory.
    """
    service = ProjectMemoryService(db)

    snapshot = service.get_latest_snapshot(project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshot found. Run a crawl first.")

    relationships = service.get_inferred_relationships(project_id)
    decision_map = service.get_decision_map(project_id)

    from models.relationship import ValidationStatus
    graph = SchemaGraph.from_snapshot_and_relationships(
        snapshot, relationships, decisions=decision_map
    )
    return graph.to_frontend_format()


class ColumnSearchRequest(BaseModel):
    terms: list[str] = Field(
        ...,
        description="List of concept names or variable names to search for across all columns.",
        min_length=1,
    )
    top_k: int = Field(default=5, ge=1, le=50, description="Max matches to return per term.")


class ColumnMatch(BaseModel):
    table: str
    column: str
    raw_type: str
    score: float
    reasons: list[str]


class TermSearchResult(BaseModel):
    term: str
    matches: list[ColumnMatch]


@router.post("/{project_id}/columns/search", response_model=list[TermSearchResult])
def search_columns(
    project_id: str,
    req: ColumnSearchRequest,
    db: Session = Depends(get_db),
) -> list[TermSearchResult]:
    """
    Given a list of concept / variable names, score every column in the latest schema
    snapshot and return the best-matching columns per term.

    This is purely lexical + structural — no LLM required. It works on any crawled
    database by splitting names into tokens and matching against table name, column name,
    raw type, and (if available) sample values.
    """
    service = ProjectMemoryService(db)
    snapshot = service.get_latest_snapshot(project_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="No snapshot found. Run a crawl first.")

    results: list[TermSearchResult] = []
    for term in req.terms:
        matches = _score_term_against_snapshot(term, snapshot, req.top_k)
        results.append(TermSearchResult(term=term, matches=matches))
    return results


# ── Column profile (live query) ───────────────────────────────────────────────

def _safe_float(v) -> float | None:
    return float(v) if v is not None else None

def _safe_round(v, decimals: int = 4) -> float | None:
    return round(float(v), decimals) if v is not None else None


@router.get("/{project_id}/columns/profile")
def profile_column(
    project_id: str,
    table: str,
    column: str,
    db: Session = Depends(get_db),
) -> dict:
    """
    Run a live summary query against the target database for a specific column.

    Numeric columns  → count, non-null count, null count, null%, min, max, mean, median, 
                       stddev, variance, sum, range, iqr, cv, p25, p75, distinct count
    Text/categorical → count, non-null count, null count, null%, distinct count, top 10 values with row share
    Boolean/date     → count, non-null count, null%, distinct count, top values

    Sends NO raw data — only aggregates. Safe for any column type.
    """
    from sqlalchemy import create_engine, text as sa_text
    from core.schema.crawler import _build_connection_url
    from models.connection import ConnectionConfig

    service = ProjectMemoryService(db)

    # Get connection config
    config_dict = service.get_connection_config(project_id)
    if not config_dict:
        raise HTTPException(status_code=404, detail="No connection config. Create a project first.")

    config = ConnectionConfig(**config_dict)

    # Verify column exists in snapshot
    snapshot = service.get_latest_snapshot(project_id)
    col_profile = None
    if snapshot:
        for t in snapshot.tables:
            if t.name.lower() == table.lower():
                for c in t.columns:
                    if c.name.lower() == column.lower():
                        col_profile = c
                        break

    try:
        if config.dialect == DatabaseDialect.AIRTABLE:
            from urllib.parse import quote as url_quote
            import math
            import httpx

            if not config.password:
                raise HTTPException(status_code=400, detail="Airtable API key missing")

            base_id = config.database
            api_key = config.password.get_secret_value()

            # Determine if numeric
            is_numeric = False
            if col_profile:
                is_numeric = col_profile.normalized_type in (
                    "integer", "bigint", "float", "decimal"
                )
            else:
                is_numeric = True

            total = 0
            non_null = 0
            distinct_values: set[str] = set()
            top_counts: dict[str, int] = {}

            num_values: list[float] = []
            num_min: float | None = None
            num_max: float | None = None
            num_sum = 0.0
            num_count = 0
            mean = 0.0
            m2 = 0.0

            def _percentile(values: list[float], q: float) -> float | None:
                if not values:
                    return None
                values_sorted = sorted(values)
                idx = (len(values_sorted) - 1) * q
                low = math.floor(idx)
                high = math.ceil(idx)
                if low == high:
                    return values_sorted[int(idx)]
                weight = idx - low
                return values_sorted[low] * (1 - weight) + values_sorted[high] * weight

            table_path = url_quote(table, safe="")
            offset: str | None = None

            with httpx.Client(
                base_url="https://api.airtable.com/v0",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=30.0,
            ) as client:
                while True:
                    params = {"pageSize": 100}
                    if offset:
                        params["offset"] = offset
                    response = client.get(f"/{base_id}/{table_path}", params=params)
                    response.raise_for_status()
                    payload = response.json()
                    records = payload.get("records", [])

                    total += len(records)
                    for record in records:
                        fields = record.get("fields", {})
                        if column not in fields or fields[column] is None:
                            continue

                        value = fields[column]
                        non_null += 1
                        value_str = str(value)
                        distinct_values.add(value_str)
                        top_counts[value_str] = top_counts.get(value_str, 0) + 1

                        if is_numeric and isinstance(value, (int, float)):
                            float_val = float(value)
                            num_values.append(float_val)
                            num_sum += float_val
                            num_count += 1
                            if num_min is None or float_val < num_min:
                                num_min = float_val
                            if num_max is None or float_val > num_max:
                                num_max = float_val

                            delta = float_val - mean
                            mean += delta / num_count
                            delta2 = float_val - mean
                            m2 += delta * delta2

                    offset = payload.get("offset")
                    if not offset:
                        break

            null_count = total - non_null
            null_pct = round((null_count / total * 100), 2) if total > 0 else 0.0
            distinct_count = len(distinct_values)

            result: dict = {
                "table": table,
                "column": column,
                "raw_type": col_profile.raw_type if col_profile else "unknown",
                "normalized_type": col_profile.normalized_type if col_profile else "unknown",
                "total_rows": total,
                "non_null_count": non_null,
                "null_count": null_count,
                "null_pct": null_pct,
                "distinct_count": distinct_count,
            }

            if is_numeric and num_count > 0:
                variance = (m2 / (num_count - 1)) if num_count > 1 else 0.0
                stddev = math.sqrt(variance) if num_count > 1 else 0.0
                median_val = _percentile(num_values, 0.5)
                p25_val = _percentile(num_values, 0.25)
                p75_val = _percentile(num_values, 0.75)

                result["min"] = _safe_float(num_min)
                result["max"] = _safe_float(num_max)
                result["mean"] = _safe_round(mean)
                result["median"] = _safe_round(median_val)
                result["stddev"] = _safe_round(stddev)
                result["variance"] = _safe_round(variance)
                result["sum"] = _safe_float(num_sum)
                result["p25"] = _safe_round(p25_val)
                result["p75"] = _safe_round(p75_val)

                if num_min is not None and num_max is not None:
                    result["range"] = num_max - num_min
                if p25_val is not None and p75_val is not None:
                    result["iqr"] = p75_val - p25_val
                if mean != 0 and stddev is not None:
                    result["cv"] = _safe_round((stddev / abs(mean)) * 100)

            if not is_numeric:
                top_values = sorted(top_counts.items(), key=lambda item: item[1], reverse=True)[:10]
                result["top_values"] = [
                    {
                        "value": value,
                        "count": count,
                        "share_pct": round(count / non_null * 100, 2) if non_null > 0 else 0.0,
                    }
                    for value, count in top_values
                ]

            result["kind"] = "numeric" if is_numeric else "categorical"
            return result

        url = _build_connection_url(config)
        engine = create_engine(url, pool_pre_ping=True, pool_size=1, max_overflow=0)
        with engine.connect() as conn:
            quoted_table = f'"{table}"'
            quoted_col = f'"{column}"'

            # Total + non-null + null counts
            counts_sql = sa_text(
                f"SELECT COUNT(*) as total, COUNT({quoted_col}) as non_null "
                f"FROM {quoted_table}"
            )
            row = conn.execute(counts_sql).fetchone()
            total = int(row[0]) if row[0] is not None else 0
            non_null = int(row[1]) if row[1] is not None else 0
            null_count = total - non_null
            null_pct = round((null_count / total * 100), 2) if total > 0 else 0.0

            # Distinct count
            distinct_sql = sa_text(
                f"SELECT COUNT(DISTINCT {quoted_col}) FROM {quoted_table}"
            )
            distinct_count = int(conn.execute(distinct_sql).scalar() or 0)

            # Determine if numeric
            is_numeric = False
            if col_profile:
                is_numeric = col_profile.normalized_type in (
                    "integer", "bigint", "float", "decimal"
                )
            else:
                # Fallback: try numeric stats and see if it works
                is_numeric = True

            result: dict = {
                "table": table,
                "column": column,
                "raw_type": col_profile.raw_type if col_profile else "unknown",
                "normalized_type": col_profile.normalized_type if col_profile else "unknown",
                "total_rows": total,
                "non_null_count": non_null,
                "null_count": null_count,
                "null_pct": null_pct,
                "distinct_count": distinct_count,
            }

            if is_numeric:
                try:
                    dialect = config.dialect.value if hasattr(config.dialect, 'value') else str(config.dialect)

                    if dialect == "postgresql":
                        num_sql = sa_text(
                            f"SELECT "
                            f"  MIN({quoted_col}), "
                            f"  MAX({quoted_col}), "
                            f"  AVG({quoted_col}::numeric), "
                            f"  STDDEV({quoted_col}::numeric), "
                            f"  VARIANCE({quoted_col}::numeric), "
                            f"  SUM({quoted_col}::numeric), "
                            f"  PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY {quoted_col}), "
                            f"  PERCENTILE_CONT(0.5)  WITHIN GROUP (ORDER BY {quoted_col}), "
                            f"  PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY {quoted_col}) "
                            f"FROM {quoted_table}"
                        )
                        num_row = conn.execute(num_sql).fetchone()
                        min_val = _safe_float(num_row[0])
                        max_val = _safe_float(num_row[1])
                        mean_val = _safe_round(num_row[2])
                        stddev_val = _safe_round(num_row[3])
                        variance_val = _safe_round(num_row[4])
                        sum_val = _safe_float(num_row[5])
                        p25_val = _safe_round(num_row[6])
                        median_val = _safe_round(num_row[7])
                        p75_val = _safe_round(num_row[8])
                        
                        result["min"]     = min_val
                        result["max"]     = max_val
                        result["mean"]    = mean_val
                        result["median"]  = median_val
                        result["stddev"]  = stddev_val
                        result["variance"] = variance_val
                        result["sum"]     = sum_val
                        result["p25"]     = p25_val
                        result["p75"]     = p75_val
                        
                        # Derived metrics
                        if min_val is not None and max_val is not None:
                            result["range"] = max_val - min_val
                        if p75_val is not None and p25_val is not None:
                            result["iqr"] = p75_val - p25_val
                        if mean_val is not None and mean_val != 0 and stddev_val is not None:
                            result["cv"] = _safe_round((stddev_val / abs(mean_val)) * 100)  # Coefficient of variation %

                    elif dialect in ("mysql", "mariadb"):
                        num_sql = sa_text(
                            f"SELECT MIN({quoted_col}), MAX({quoted_col}), "
                            f"AVG({quoted_col}), STDDEV({quoted_col}), VARIANCE({quoted_col}), SUM({quoted_col}) "
                            f"FROM {quoted_table}"
                        )
                        num_row = conn.execute(num_sql).fetchone()
                        min_val = _safe_float(num_row[0])
                        max_val = _safe_float(num_row[1])
                        mean_val = _safe_round(num_row[2])
                        stddev_val = _safe_round(num_row[3])
                        variance_val = _safe_round(num_row[4])
                        sum_val = _safe_float(num_row[5])
                        
                        result["min"]     = min_val
                        result["max"]     = max_val
                        result["mean"]    = mean_val
                        result["median"]  = mean_val  # MySQL doesn't have built-in MEDIAN, approximate with mean
                        result["stddev"]  = stddev_val
                        result["variance"] = variance_val
                        result["sum"]     = sum_val
                        
                        # Derived metrics
                        if min_val is not None and max_val is not None:
                            result["range"] = max_val - min_val
                        if mean_val is not None and mean_val != 0 and stddev_val is not None:
                            result["cv"] = _safe_round((stddev_val / abs(mean_val)) * 100)

                    elif dialect == "mssql":
                        num_sql = sa_text(
                            f"SELECT MIN({quoted_col}), MAX({quoted_col}), "
                            f"AVG(CAST({quoted_col} AS FLOAT)), STDEV({quoted_col}), VAR({quoted_col}), SUM({quoted_col}) "
                            f"FROM {quoted_table}"
                        )
                        num_row = conn.execute(num_sql).fetchone()
                        min_val = _safe_float(num_row[0])
                        max_val = _safe_float(num_row[1])
                        mean_val = _safe_round(num_row[2])
                        stddev_val = _safe_round(num_row[3])
                        variance_val = _safe_round(num_row[4])
                        sum_val = _safe_float(num_row[5])
                        
                        result["min"]     = min_val
                        result["max"]     = max_val
                        result["mean"]    = mean_val
                        result["median"]  = mean_val  # MSSQL doesn't have built-in MEDIAN, approximate with mean
                        result["stddev"]  = stddev_val
                        result["variance"] = variance_val
                        result["sum"]     = sum_val
                        
                        # Derived metrics
                        if min_val is not None and max_val is not None:
                            result["range"] = max_val - min_val
                        if mean_val is not None and mean_val != 0 and stddev_val is not None:
                            result["cv"] = _safe_round((stddev_val / abs(mean_val)) * 100)

                    else:
                        # SQLite and others — basic stats only
                        num_sql = sa_text(
                            f"SELECT MIN({quoted_col}), MAX({quoted_col}), "
                            f"AVG({quoted_col}), SUM({quoted_col}) "
                            f"FROM {quoted_table}"
                        )
                        num_row = conn.execute(num_sql).fetchone()
                        min_val = _safe_float(num_row[0])
                        max_val = _safe_float(num_row[1])
                        mean_val = _safe_round(num_row[2])
                        sum_val = _safe_float(num_row[3])
                        
                        result["min"]  = min_val
                        result["max"]  = max_val
                        result["mean"] = mean_val
                        result["sum"]  = sum_val
                        
                        # Derived metrics
                        if min_val is not None and max_val is not None:
                            result["range"] = max_val - min_val

                except Exception:
                    # Not truly numeric — fall through to categorical
                    is_numeric = False

            if not is_numeric:
                # Top 10 categories with counts + share
                top_sql = sa_text(
                    f"SELECT {quoted_col}, COUNT(*) as cnt "
                    f"FROM {quoted_table} "
                    f"WHERE {quoted_col} IS NOT NULL "
                    f"GROUP BY {quoted_col} "
                    f"ORDER BY cnt DESC "
                    f"LIMIT 10"
                )
                top_rows = conn.execute(top_sql).fetchall()
                result["top_values"] = [
                    {
                        "value": str(r[0]),
                        "count": int(r[1]),
                        "share_pct": round(int(r[1]) / non_null * 100, 2) if non_null > 0 else 0.0,
                    }
                    for r in top_rows
                ]

            result["kind"] = "numeric" if is_numeric else "categorical"
            return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# Column search scoring — fully generic, no domain assumptions
# ──────────────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Split snake_case, camelCase, spaces, and hyphens into lowercase tokens."""
    # Split on non-alphanumeric boundaries then camelCase
    step1 = re.sub(r'[_\-\s]+', ' ', text)
    step2 = re.sub(r'([a-z])([A-Z])', r'\1 \2', step1)
    return {t.lower() for t in step2.split() if t}


def _score_term_against_snapshot(term: str, snapshot, top_k: int) -> list[ColumnMatch]:
    from models.schema import SchemaSnapshot
    term_tokens = _tokenize(term)
    candidates: list[tuple[float, ColumnMatch]] = []

    for table in snapshot.tables:
        table_tokens = _tokenize(table.name)
        for col in table.columns:
            score, reasons = _score_column(term, term_tokens, table.name, table_tokens, col)
            if score > 0:
                candidates.append((score, ColumnMatch(
                    table=table.name,
                    column=col.name,
                    raw_type=col.raw_type,
                    score=round(score, 4),
                    reasons=reasons,
                )))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in candidates[:top_k]]


def _score_column(
    term: str,
    term_tokens: set[str],
    table_name: str,
    table_tokens: set[str],
    col,
) -> tuple[float, list[str]]:
    """
    Returns (score, reasons). Score is in [0, ∞). Higher = better match.

    Scoring signals (no domain knowledge — purely structural):
      1. Exact column name match          → 1.0
      2. Token overlap with column name   → Jaccard × 0.7
      3. Partial token overlap            → overlap_frac × 0.5
      4. Token overlap with table name    → Jaccard × 0.3
      5. Term appears in sample values    → +0.2
      6. Normalized type hint match       → +0.15
    """
    score = 0.0
    reasons: list[str] = []

    col_tokens = _tokenize(col.name)

    # 1. Exact full name match
    if col.name.lower() == term.lower():
        score += 1.0
        reasons.append("exact column name match")

    # 2. Jaccard similarity between term tokens and column tokens
    if term_tokens and col_tokens:
        intersection = term_tokens & col_tokens
        union = term_tokens | col_tokens
        jaccard = len(intersection) / len(union)
        if jaccard > 0:
            score += jaccard * 0.7
            reasons.append(f"token overlap with column name ({', '.join(sorted(intersection))})")

        # 3. Partial: all term tokens appear in column tokens (handles plurals etc.)
        if term_tokens <= col_tokens and len(term_tokens) > 0:
            score += 0.5
            reasons.append("all term tokens contained in column name")

    # 4. Jaccard with table name (weaker signal — context)
    if term_tokens and table_tokens:
        t_inter = term_tokens & table_tokens
        t_union = term_tokens | table_tokens
        t_jaccard = len(t_inter) / len(t_union)
        if t_jaccard > 0:
            score += t_jaccard * 0.3
            reasons.append(f"token overlap with table name ({', '.join(sorted(t_inter))})")

    # 5. Term appears literally in sample values
    if col.sample_values:
        term_lower = term.lower()
        for sv in col.sample_values[:20]:
            if term_lower in str(sv).lower():
                score += 0.2
                reasons.append(f"term found in sample values")
                break

    # 6. Normalized type hint: if the term itself names a type (e.g. "timestamp", "id", "uuid")
    TYPE_HINTS: dict[str, set[str]] = {
        "integer": {"id", "count", "num", "number", "qty", "quantity", "age", "rank", "score", "index"},
        "timestamp": {"date", "time", "at", "on", "when", "created", "updated", "ts"},
        "boolean": {"is", "has", "flag", "active", "enabled", "deleted", "cancelled", "approved"},
        "uuid": {"id", "uuid", "guid", "key"},
        "varchar": {"name", "label", "code", "status", "type", "reason", "note", "comment"},
    }
    norm_type = col.normalized_type if hasattr(col, "normalized_type") else ""
    if norm_type in TYPE_HINTS:
        if term_tokens & TYPE_HINTS[norm_type]:
            score += 0.15
            reasons.append(f"column type ({norm_type}) consistent with term semantics")

    return score, reasons


def _deserialize_connection_config(config_dict: dict) -> ConnectionConfig:
    """Reconstruct a ConnectionConfig from the stored JSON dict."""
    from pydantic import SecretStr

    raw_password = config_dict.get("password")
    if raw_password and raw_password != "***":
        config_dict = {**config_dict, "password": SecretStr(raw_password)}
    else:
        config_dict = {**config_dict, "password": None}

    return ConnectionConfig.model_validate(config_dict)
