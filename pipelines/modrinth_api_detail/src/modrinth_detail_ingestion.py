#!/usr/bin/env python
# coding: utf-8

# # Modrinth Project Version Ingestion
# 
# This notebook performs the detailed Modrinth version pull without depending on the legacy `Bundle` object.
# 
# Flow:
# 
# 1. Load pipeline settings from `stream-config.yml`.
# 2. Build Bronze/Silver DuckDB paths with the shared database/path utilities.
# 3. Read `project_id` and `project_type` from the latest Modrinth General Silver table.
# 4. Fetch `/project/{project_id}/version` asynchronously for every project using the shared `ModrinthRateLimiter`.
# 5. Preserve each complete version response as raw JSON in Bronze.
# 6. Update the generalized ingestion log for every project type.
# 
# The project listing/search API is intentionally not called here. Modrinth General Silver defines the project universe for this job.
# 

# In[2]:


import os
import asyncio
import json
import time
import uuid
from datetime import datetime, timezone

import duckdb
import httpx
import polars as pl
import yaml
import argparse
import hashlib

from shared_code.api.modrinth_rate_limiter import ModrinthRateLimiter
from shared_code.database.directory_creation import *
from shared_code.database.database_and_schema_creation import *
from pipelines.modrinth_api_detail.schemas.modrinth_detail_schemas import *


# ## Progress tracking
# 
# The detailed endpoint requires one request per project. Progress distinguishes project requests completed, version objects fetched, project payload rows written, and failed project requests.
# 

# In[3]:


class IngestionProgress:
    """Mutable progress shared by concurrent version-fetch tasks."""

    def __init__(
        self,
        total_projects: int,
        project_type: str,
    ) -> None:
        self.total_projects = total_projects
        self.project_type = project_type
        self.completed_projects = 0
        self.failed_projects = 0
        self.versions_fetched = 0
        self.project_payloads_written = 0
        self.start_time = time.perf_counter()
        self.last_print_time = 0.0
        self.lock = asyncio.Lock()


# In[4]:


async def print_progress(
    progress: IngestionProgress,
    force: bool = False,
) -> None:
    """Refresh one console line with current ingestion progress."""
    now = time.perf_counter()

    if not force and (now - progress.last_print_time) < 0.25:
        return

    elapsed_seconds = max(
        now - progress.start_time,
        0.001,
    )

    percent_complete = (
        progress.completed_projects
        / progress.total_projects
        * 100
        if progress.total_projects
        else 0.0
    )

    requests_per_minute = (
        progress.completed_projects
        / elapsed_seconds
        * 60
    )

    print(
        f"\r\t(INFO) "
        f"projects={progress.completed_projects:,}/{progress.total_projects:,} "
        f"({percent_complete:6.2f}%) | "
        f"versions={progress.versions_fetched:,} | "
        f"payloads_written={progress.project_payloads_written:,} | "
        f"failed={progress.failed_projects:,} | "
        f"pace={requests_per_minute:,.1f} req/min",
        end="",
        flush=True,
    )

    progress.last_print_time = now


async def mark_project_complete(
    progress: IngestionProgress,
    versions_fetched: int,
    failed: bool = False,
) -> None:
    async with progress.lock:
        progress.completed_projects += 1
        progress.versions_fetched += versions_fetched

        if failed:
            progress.failed_projects += 1

        await print_progress(progress)


async def mark_payloads_written(
    progress: IngestionProgress,
    payloads_written: int,
) -> None:
    async with progress.lock:
        progress.project_payloads_written += payloads_written
        await print_progress(progress)


# ## HTTP helper
# 
# All API requests use one shared `httpx.AsyncClient` and the same shared rate-limiter implementation used by the Modrinth General pipeline.
# 

# In[5]:


async def _get_json_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    rate_limiter: ModrinthRateLimiter,
    params: dict | None = None,
    max_retries: int = 6,
) -> dict | list:
    last_error = None

    for attempt in range(max_retries):
        await rate_limiter.wait_if_paused()

        try:
            # Some limiter implementations also expose explicit request-slot
            # pacing. Use it when available without requiring it.
            wait_for_request_slot = getattr(
                rate_limiter,
                "wait_for_request_slot",
                None,
            )

            if wait_for_request_slot is not None:
                await wait_for_request_slot()

            async with rate_limiter.semaphore:
                response = await client.get(
                    url,
                    params=params,
                )

            if response.status_code == 429:
                update_from_429 = getattr(
                    rate_limiter,
                    "update_from_429",
                    None,
                )

                if update_from_429 is not None:
                    await update_from_429(response)

                await asyncio.sleep(
                    rate_limiter.full_reset_seconds
                )
                continue

            response.raise_for_status()

            update_from_response = getattr(
                rate_limiter,
                "update_from_response",
                None,
            )

            if update_from_response is not None:
                await update_from_response(response)

            return response.json()

        except (
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.RemoteProtocolError,
            httpx.NetworkError,
        ) as exc:
            last_error = exc
            await asyncio.sleep(
                rate_limiter.full_reset_seconds
            )

        except httpx.HTTPStatusError as exc:
            last_error = exc

            if 500 <= exc.response.status_code < 600:
                await asyncio.sleep(
                    rate_limiter.full_reset_seconds
                )
                continue

            raise

    raise RuntimeError(
        f"Exceeded retries for {url}. Last error: {last_error}"
    )


# ## Read the project universe from Modrinth General Silver
# 
# Only `project_id` and `project_type` are required. The detailed pipeline uses the latest current-state Silver project-listing table as its input universe.
# 

# In[6]:


def read_base_projects(
    silver_db_path: str,
    project_listings_table_name: str,
) -> pl.DataFrame:
    """Read the distinct projects that should receive a version API call."""
    with duckdb.connect(
        silver_db_path,
        read_only=True,
    ) as silver_con:
        table_columns = {
            row[0]
            for row in silver_con.execute(
                f"DESCRIBE {project_listings_table_name}"
            ).fetchall()
        }

        required_columns = {
            "project_id",
            "project_type",
        }

        missing_columns = required_columns - table_columns

        if missing_columns:
            raise ValueError(
                f"{project_listings_table_name} is missing required columns: "
                f"{sorted(missing_columns)}"
            )

        projects_df = silver_con.execute(
            f"""
            SELECT DISTINCT
                project_id,
                project_type
            FROM {project_listings_table_name}
            WHERE project_id IS NOT NULL
              AND project_type IS NOT NULL
            ORDER BY
                project_type,
                project_id
            """
        ).pl()

    return projects_df


def validate_version_payload_table_schema(
    bronze_db_path: str,
    table_name: str,
) -> None:
    """Fail early if an older flattened Bronze detail table still exists."""
    expected_columns = {
        "run_id",
        "project_type",
        "project_id",
        "payload",
        "hashed_payload",
        "c_pull_timestamp_utc",
    }

    with duckdb.connect(
        bronze_db_path,
        read_only=True,
    ) as bronze_con:
        actual_columns = {
            row[0]
            for row in bronze_con.execute(
                f"DESCRIBE {table_name}"
            ).fetchall()
        }

    if actual_columns != expected_columns:
        raise ValueError(
            f"{table_name} does not match the raw JSON payload schema. "
            f"Expected columns: {sorted(expected_columns)}. "
            f"Found: {sorted(actual_columns)}. "
            "Drop or migrate the old detail table before rerunning ingestion."
        )


# ## Fetch raw project version payloads
# 
# Each project produces one API request. The complete list returned by Modrinth is preserved unchanged as that project's Bronze JSON payload.
# 

# In[7]:


async def fetch_project_versions(
    client: httpx.AsyncClient,
    rate_limiter: ModrinthRateLimiter,
    source_url: str,
    project: dict,
    progress: IngestionProgress,
) -> dict:
    """Fetch and return the complete version payload for one project."""
    project_id = project["project_id"]

    try:
        versions = await _get_json_with_backoff(
            client=client,
            url=(
                f"{source_url}/project/"
                f"{project_id}/version"
            ),
            rate_limiter=rate_limiter,
            params={
                "include_changelog": "false",
            },
        )

        if not isinstance(versions, list):
            raise TypeError(
                f"Expected a list of versions for {project_id}, "
                f"got {type(versions).__name__}"
            )

        await mark_project_complete(
            progress=progress,
            versions_fetched=len(versions),
        )

        return {
            "project_type": project["project_type"],
            "project_id": project_id,
            "payload": versions,
            "c_pull_timestamp_utc": datetime.now(timezone.utc),
            "error": None,
        }

    except Exception as exc:
        await mark_project_complete(
            progress=progress,
            versions_fetched=0,
            failed=True,
        )

        return {
            "project_type": project["project_type"],
            "project_id": project_id,
            "payload": [],
            "c_pull_timestamp_utc": None,
            "error": exc,
        }


# ## Build and write Bronze payload rows
# 
# One successful project API response becomes exactly one Bronze row:
# 
# - `run_id`
# - `project_type`
# - `project_id`
# - complete `payload` JSON array
# - `c_pull_timestamp_utc`
# 
# Bronze stays raw. Flattening and datatype normalization happen in the Bronze-to-Silver notebook.
# 

# In[8]:


def build_version_payload_rows(
    run_id: str,
    results: list[dict],
) -> list[tuple]:
    """Convert successful API results into Bronze payload rows."""

    rows = []

    for result in results:
        if result["error"] is not None:
            continue

        payload_json = json.dumps(
            result["payload"]
        )

        hashed_payload = hash_payload(
            result["payload"]
        )

        rows.append(
            (
                run_id,
                result["project_type"],
                result["project_id"],
                payload_json,
                hashed_payload,
                result["c_pull_timestamp_utc"],
            )
        )

    return rows


def write_version_payload_rows(
    bronze_con: duckdb.DuckDBPyConnection,
    table_name: str,
    version_rows: list[tuple],
) -> int:
    """Write a batch of raw project-version JSON payloads to Bronze."""
    if not version_rows:
        return 0

    insert_sql = f"""
        INSERT OR REPLACE INTO {table_name}
        (
            run_id,
            project_type,
            project_id,
            payload,
            hashed_payload,
            c_pull_timestamp_utc
        )
        VALUES (?, ?, ?, ?, ?, ?)
    """

    bronze_con.executemany(
        insert_sql,
        version_rows,
    )

    return len(version_rows)


# In[9]:


async def ingest_project_type_versions(
    run_id: str,
    table_name: str,
    source_url: str,
    project_type: str,
    projects_df: pl.DataFrame,
    client: httpx.AsyncClient,
    rate_limiter: ModrinthRateLimiter,
    bronze_con: duckdb.DuckDBPyConnection,
    project_batch_size: int = 250,
) -> dict:
    """Fetch and persist all version payloads for one project type."""
    project_type_df = projects_df.filter(
        pl.col("project_type") == project_type
    )

    projects = project_type_df.to_dicts()
    total_projects = len(projects)

    progress = IngestionProgress(
        total_projects=total_projects,
        project_type=project_type,
    )

    failed_project_ids = []
    start_time = time.perf_counter()

    await print_progress(
        progress,
        force=True,
    )

    for start_idx in range(
        0,
        total_projects,
        project_batch_size,
    ):
        project_batch = projects[
            start_idx:start_idx + project_batch_size
        ]

        results = await asyncio.gather(
            *[
                fetch_project_versions(
                    client=client,
                    rate_limiter=rate_limiter,
                    source_url=source_url,
                    project=project,
                    progress=progress,
                )
                for project in project_batch
            ]
        )

        failed_project_ids.extend(
            result["project_id"]
            for result in results
            if result["error"] is not None
        )

        version_rows = build_version_payload_rows(
            run_id=run_id,
            results=results,
        )

        payloads_written = write_version_payload_rows(
            bronze_con=bronze_con,
            table_name=table_name,
            version_rows=version_rows,
        )

        await mark_payloads_written(
            progress=progress,
            payloads_written=payloads_written,
        )

    await print_progress(
        progress,
        force=True,
    )
    print()

    duration_seconds = time.perf_counter() - start_time

    if failed_project_ids:
        failed_preview = ", ".join(
            failed_project_ids[:10]
        )
        print(
            f"\t(WARN) failed projects: {len(failed_project_ids):,} | "
            f"first IDs: {failed_preview}"
        )

    return {
        "run_id": run_id,
        "project_type": project_type,
        "projects_processed": progress.completed_projects,
        "projects_failed": progress.failed_projects,
        "versions_fetched": progress.versions_fetched,
        "project_payloads_written": progress.project_payloads_written,
        "failed_project_ids": failed_project_ids,
        "duration_seconds": duration_seconds,
    }


# ## Ingestion logging
# 
# The log schema and metric meanings match the Modrinth General pipeline. One log row is written per `run_id + ingestion_type + project_type`.
# 

# In[10]:


def start_ingestion_log(
    db_path: str,
    ingestion_log: str,
    source_url: str,
    run_id: str,
    ingestion_type: str,
    project_type: str,
) -> None:
    insert_sql = f"""
        INSERT INTO {ingestion_log}
        (
            run_id,
            ingestion_type,
            api_url,
            project_type,
            status,
            start_time
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    """

    with duckdb.connect(db_path) as bronze_con:
        bronze_con.execute(
            insert_sql,
            [
                run_id,
                ingestion_type,
                source_url,
                project_type,
                "running",
            ],
        )


# In[11]:


def finish_ingestion_log(
    db_path: str,
    ingestion_log: str,
    run_id: str,
    ingestion_type: str,
    project_type: str,
    status: str,
    records_processed: int = 0,
    records_written: int = 0,
    records_failed: int = 0,
    records_skipped: int = 0,
    nested_records_fetched: int | None = None,
    failed_record_ids: list[str] | None = None,
    skipped_record_ids: list[str] | None = None,
    error_message: str | None = None,
) -> None:
    update_sql = f"""
        UPDATE {ingestion_log}
        SET
            status = ?,
            records_processed = ?,
            records_written = ?,
            records_failed = ?,
            records_skipped = ?,
            nested_records_fetched = ?,
            failed_record_ids = ?,
            skipped_record_ids = ?,
            error_message = ?,
            end_time = CURRENT_TIMESTAMP,
            duration_seconds = EXTRACT(
                EPOCH FROM (
                    CURRENT_TIMESTAMP - start_time
                )
            )
        WHERE run_id = ?
          AND ingestion_type = ?
          AND project_type = ?
    """

    with duckdb.connect(db_path) as bronze_con:
        bronze_con.execute(
            update_sql,
            [
                status,
                records_processed,
                records_written,
                records_failed,
                records_skipped,
                nested_records_fetched,
                failed_record_ids,
                skipped_record_ids,
                error_message,
                run_id,
                ingestion_type,
                project_type,
            ],
        )

def hash_payload(payload: list | dict) -> str:
    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical_payload.encode("utf-8")
    ).hexdigest()


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--env",
        choices=[
            "dev",
            "test",
            "prod",
        ],
        default="dev",
    )
    
    parser.add_argument(
        "--search-page-concurrency",
        type=int,
        default=8,
    )
    
    return parser.parse_args()


async def ingestion(env: str) -> pl.DataFrame:
    
    src_dir = os.path.dirname(
            os.path.abspath(__file__)
        )
    
    pipeline_dir = os.path.abspath(
        os.path.join(
            src_dir,
            "..",
        )
    )
    project_root = os.path.abspath(
        os.path.join(
            src_dir,
            "..",
            "..",
            "..",
        )
    )
        
    config_path = os.path.join(pipeline_dir, "stream-config.yml")
    
    with open(config_path, "r") as file:
        config_data = yaml.safe_load(file)

    upstream_config = config_data["upstream"]
    headers = config_data["main"]["headers"]
    ingestion_log = config_data["main"]["ingestion-log"]

    streams = config_data["streams"]

    detail_stream = next(
        (
            stream
            for stream in streams
            if stream["name"] == "modrinth_project_versions"
        ),
        None,
    )

    if detail_stream is None:
        raise ValueError(
            "stream-config.yml must contain a stream named "
            "'modrinth_project_versions'."
        )

    source_url = detail_stream["source-url"]
    table_name = detail_stream["table-name"]
    concurrency_limit = detail_stream["concurrency-limit"]
    project_batch_size = detail_stream.get(
        "project-batch-size",
        250,
    )

    bronze_path = os.path.join(
        project_root,
        config_data["main"]["parent-folder"],
        "bronze",
        env,
        build_db_filename(source_url),
    )

    silver_path = os.path.join(
        project_root,
        config_data["main"]["parent-folder"],
        "silver",
        env,
        build_db_filename(source_url),
    )

        # Create the Bronze layer directory and initialize the detail target table.
    build_layer_directory(
        os.path.dirname(bronze_path)
    )

    bronze_schemas = [
        build_bronze_modrinth_project_versions_schema(
            table_name
        ),
        build_ingestion_log_schema(
            ingestion_log
        ),
    ]

    init_db(
        bronze_path,
        bronze_schemas,
    )

    # Fail before making API calls if an older flattened detail table exists.
    validate_version_payload_table_schema(
        bronze_db_path=bronze_path,
        table_name=table_name,
    )

    # Modrinth General Silver is the authoritative project universe.
    base_projects_df = read_base_projects(
        silver_db_path=silver_path,
        project_listings_table_name=upstream_config['project-listings-table-name'],
    )

    project_types = (
        base_projects_df
        .select("project_type")
        .unique()
        .sort("project_type")
        .to_series()
        .to_list()
    )

    # TEMPORARY TEST OVERRIDE:
    # project_types = ["mod"]
    
    run_id = str(uuid.uuid4())
    ingestion_type = "project_versions"
    summaries = []

    total_projects = base_projects_df.height

    print(
        f"[INFO] Starting detailed version ingestion | "
        f"run_id={run_id} | "
        f"projects={total_projects:,} | "
        f"project_types={len(project_types):,}"
    )

    rate_limiter = ModrinthRateLimiter(
        max_concurrency=concurrency_limit,
        full_reset_seconds=61,
    )

    timeout = httpx.Timeout(
        connect=10.0,
        read=60.0,
        write=10.0,
        pool=60.0,
    )

    limits = httpx.Limits(
        max_connections=max(
            10,
            concurrency_limit * 2,
        ),
        max_keepalive_connections=max(
            5,
            concurrency_limit,
        ),
    )

    async with httpx.AsyncClient(
        headers=headers,
        timeout=timeout,
        limits=limits,
        follow_redirects=True,
    ) as client:
        with duckdb.connect(bronze_path) as bronze_con:
            for idx, project_type in enumerate(project_types):
                print(
                    f"({idx + 1}/{len(project_types)}) "
                    f"Ingesting project versions: {project_type}"
                )

                start_ingestion_log(
                    db_path=bronze_path,
                    ingestion_log=ingestion_log,
                    source_url=source_url,
                    run_id=run_id,
                    ingestion_type=ingestion_type,
                    project_type=project_type,
                )

                try:
                    summary = await ingest_project_type_versions(
                        run_id=run_id,
                        table_name=table_name,
                        source_url=source_url,
                        project_type=project_type,
                        projects_df=base_projects_df,
                        client=client,
                        rate_limiter=rate_limiter,
                        bronze_con=bronze_con,
                        project_batch_size=project_batch_size,
                    )

                    summaries.append(summary)

                    records_processed = (
                        summary["projects_processed"]
                    )

                    records_written = (
                        summary["project_payloads_written"]
                    )

                    records_failed = (
                        summary["projects_failed"]
                    )

                    records_skipped = 0

                    nested_records_fetched = (
                        summary["versions_fetched"]
                    )

                    failed_record_ids = (
                        summary["failed_project_ids"]
                    )

                    print(
                        f"\t(INFO) projects processed: "
                        f"{records_processed:,}"
                    )

                    print(
                        f"\t(INFO) project payloads written: "
                        f"{records_written:,}"
                    )

                    print(
                        f"\t(INFO) projects failed: "
                        f"{records_failed:,}"
                    )

                    print(
                        f"\t(INFO) versions fetched: "
                        f"{nested_records_fetched:,}"
                    )

                    finish_ingestion_log(
                        db_path=bronze_path,
                        ingestion_log=ingestion_log,
                        run_id=run_id,
                        ingestion_type=ingestion_type,
                        project_type=project_type,
                        status="success",
                        records_processed=records_processed,
                        records_written=records_written,
                        records_failed=records_failed,
                        records_skipped=records_skipped,
                        nested_records_fetched=nested_records_fetched,
                        failed_record_ids=failed_record_ids,
                        skipped_record_ids=None,
                        error_message=None,
                    )

                except Exception as exc:
                    finish_ingestion_log(
                        db_path=bronze_path,
                        ingestion_log=ingestion_log,
                        run_id=run_id,
                        ingestion_type=ingestion_type,
                        project_type=project_type,
                        status="failed",
                        error_message=str(exc),
                    )

                    print(
                        f"\t(ERROR) Failed to ingest versions for "
                        f"project_type {project_type}: {exc}"
                    )

                    continue

    if not summaries:
        return pl.DataFrame()

    summary_df = pl.DataFrame(summaries)

    # Keep the visible summary output compatible with the original notebook.
    return summary_df.select(
        "run_id",
        "project_type",
        "projects_processed",
        "projects_failed",
        "versions_fetched",
        "project_payloads_written",
        "duration_seconds",
    )

if __name__ == "__main__":
    args = parse_args()
    
    version_ingestion_summary_df = asyncio.run(ingestion(
        env=args.env
    ))

