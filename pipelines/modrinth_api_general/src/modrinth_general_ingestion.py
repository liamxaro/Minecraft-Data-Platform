import os
import duckdb
import httpx
import json
import asyncio
from datetime import datetime, timezone
import requests
import uuid
import polars as pl
import time
import yaml
import argparse

from shared_code.api.modrinth_rate_limiter import ModrinthRateLimiter
from shared_code.database.directory_creation import *
from shared_code.database.database_and_schema_creation import *
from pipelines.modrinth_api_general.schemas.modrinth_general_schemas import *

#Any arguments you want to inherit from the DAG come through this function
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

def get_modrinth_project_types(url: str, headers: dict) -> list[str]:
    """
    Retrieve valid Modrinth project types from the API.
    """
    url = f"{url}/tag/project_type"

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    project_types = response.json()

    if not isinstance(project_types, list):
        raise TypeError(f"Expected list from Modrinth API, got {type(project_types).__name__}")

    if not all(isinstance(projectType, str) for projectType in project_types):
        raise TypeError("Expected all project types to be strings")

    return project_types

async def _get_json_with_backoff(
    client: httpx.AsyncClient,
    url: str,
    rate_limiter: ModrinthRateLimiter,
    params: dict | None = None,
    max_retries: int = 6,
) -> dict:
    last_error = None

    for attempt in range(max_retries):
        await rate_limiter.wait_if_paused()

        try:
            async with rate_limiter.semaphore:
                response = await client.get(url, params=params)

            if response.status_code == 429:
                await rate_limiter.update_from_429(response)
                await asyncio.sleep(rate_limiter.full_reset_seconds)
                continue

            response.raise_for_status()

            await rate_limiter.update_from_response(response)
            return response.json()

        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.NetworkError) as e:
            last_error = e
            await asyncio.sleep(rate_limiter.full_reset_seconds)

        except httpx.HTTPStatusError as e:
            last_error = e

            if 500 <= e.response.status_code < 600:
                await asyncio.sleep(rate_limiter.full_reset_seconds)
                continue

            raise

    raise RuntimeError(f"Exceeded retries for {url}. Last error: {last_error}")

async def fetch_search_page(
    client: httpx.AsyncClient,
    rate_limiter: ModrinthRateLimiter,
    source_url: str,
    search_limit: int,
    project_type: str,
    offset: int,
) -> tuple[int, list[dict]]:

    data = await _get_json_with_backoff(
        client=client,
        url=f"{source_url}/search",
        rate_limiter=rate_limiter,
        params={
            "limit": search_limit,
            "offset": offset,
            "facets": f'[["project_type:{project_type}"]]',
        },
    )

    return offset, data.get("hits", [])

async def ingest_all_project_listings(
    run_id: str,
    db_path: str,
    table_name: str,
    source_url: str,
    project_type: str,
    headers: dict,
    search_limit: int,
    search_page_concurrency: int = 8,
) -> tuple[int, list[str]]:

    insert_sql = f"""
        INSERT INTO {table_name}
        (
            run_id,
            project_type,
            project_id,
            payload,
            hashed_payload,
            c_pull_timestamp_utc
        )
        SELECT
            run_id,
            project_type,
            project_id,
            payload,
            md5(CAST(payload AS VARCHAR)) AS hashed_payload,
            c_pull_timestamp_utc
        FROM (
            SELECT
                ? AS run_id,
                ? AS project_type,
                ? AS project_id,
                CAST(? AS JSON) AS payload,
                ? AS c_pull_timestamp_utc
        )
    """

    total_written = 0
    next_offset = 0

    seen_project_ids = set()
    duplicate_project_ids = []

    page_size = search_limit
    start_time = time.perf_counter()

    rate_limiter = ModrinthRateLimiter(
        max_concurrency=search_page_concurrency,
        full_reset_seconds=61,
    )

    with duckdb.connect(db_path) as bronze_con:

        async with httpx.AsyncClient(
            headers=headers,
            timeout=60,
        ) as client:

            while True:

                offsets = [
                    next_offset + (i * page_size)
                    for i in range(search_page_concurrency)
                ]

                tasks = [
                    fetch_search_page(
                        client=client,
                        rate_limiter=rate_limiter,
                        source_url=source_url,
                        search_limit=search_limit,
                        project_type=project_type,
                        offset=offset,
                    )
                    for offset in offsets
                ]

                results = await asyncio.gather(*tasks)

                results.sort(key=lambda x: x[0])

                rows = []
                reached_end = False
                pull_timestamp = datetime.now(timezone.utc)

                for offset, hits in results:

                    if len(hits) < page_size:
                        reached_end = True

                    for h in hits:
                        project_id = h["project_id"]

                        if project_id in seen_project_ids:
                            duplicate_project_ids.append(project_id)
                            continue

                        seen_project_ids.add(project_id)

                        rows.append(
                            (
                                run_id,
                                project_type,
                                project_id,
                                json.dumps(h, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
                                pull_timestamp,
                            )
                        )

                if rows:
                    bronze_con.executemany(
                        insert_sql,
                        rows,
                    )

                    total_written += len(rows)

                elapsed_seconds = time.perf_counter() - start_time

                rows_per_second = (
                    total_written / elapsed_seconds
                    if elapsed_seconds > 0
                    else 0
                )

                print(
                    f"\r\t(INFO) "
                    f"ingested={total_written:,} | "
                    f"duplicates={len(duplicate_project_ids):,} | "
                    f"rate={rows_per_second:,.1f} rows/sec | "
                    f"offset={next_offset:,}",
                    end="",
                    flush=True,
                )

                if reached_end:
                    break

                next_offset += page_size * search_page_concurrency

    print()

    return total_written, duplicate_project_ids


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

    with duckdb.connect(
        db_path
    ) as bronze_con:

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

    with duckdb.connect(
        db_path
    ) as bronze_con:

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


async def ingestion(env: str):
    
    try:
        src_dir = os.path.dirname(
            os.path.abspath(__file__)
        )
    except NameError:
        src_dir = os.getcwd()

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
    
    headers = config_data['main']['headers']
    ingestion_log = config_data['main']['ingestion-log']

    streams = config_data['streams']
    source_url = streams[0]['source-url']
    table_name = streams[0]['table-name']
    search_limit = streams[0]['search-limit']
    concurrency_limit = streams[0]['concurrency-limit']
    bronze_path = os.path.join(project_root, config_data['main']['parent-folder'], 'bronze', env, build_db_filename(streams[0]['source-url']))
    silver_path = os.path.join(project_root, config_data['main']['parent-folder'], 'silver', env, build_db_filename(streams[0]['source-url']))



    build_layer_directory(os.path.dirname(bronze_path))
    bronze_schemas = [build_bronze_modrinth_project_listings_schema(table_name), build_ingestion_log_schema(ingestion_log)]
    init_db(bronze_path, bronze_schemas)

    # retrieve supported Modrinth project types
    # mod, modpack, resourcepack, shader, datapack, plugin, minecraft_java_server
    
    with duckdb.connect(silver_path, read_only=True) as silver_con:
        project_types = [
            row[0].strip().lower() for row in silver_con.execute("SELECT DISTINCT project_type FROM modrinth_project_types").fetchall()
            ]
    #project_types = get_modrinth_project_types(source_url, headers)

    # one run_id represents this entire project-listings ingestion execution
    run_id = str(uuid.uuid4())

    ingestion_type = "project_listings"

    for idx, project_type in enumerate(project_types):

        print(
            f"({idx + 1}/{len(project_types)}) "
            f"Ingesting project_type: {project_type}"
        )

        # create the ingestion-log row before processing begins
        start_ingestion_log(
            db_path=bronze_path,
            ingestion_log=ingestion_log,
            source_url=source_url,
            run_id=run_id,
            ingestion_type=ingestion_type,
            project_type=project_type,
        )

        try:
            # retrieve and write project listings for this project type
            records_written, skipped_record_ids = (
                await ingest_all_project_listings(
                    run_id=run_id,
                    db_path = bronze_path,
                    source_url=source_url,
                    table_name = table_name,
                    project_type = project_type,
                    headers = headers,
                    search_limit = search_limit,
                    search_page_concurrency = concurrency_limit
                )
            )
            
            if records_written == 0:
                raise ValueError(
                    f"No project listings were written "
                    f"for project_type={project_type}."
                )

            records_skipped = len(skipped_record_ids)

            # processed includes both written and intentionally skipped records
            records_processed = (
                records_written
                + records_skipped
            )

            print(
                f"\t(INFO) records processed: "
                f"{records_processed:,}"
            )

            print(
                f"\t(INFO) project listings written: "
                f"{records_written:,}"
            )

            print(
                f"\t(INFO) duplicate listings skipped: "
                f"{records_skipped:,}"
            )

            # complete the ingestion-log row
            finish_ingestion_log(
                run_id=run_id,
                db_path=bronze_path,
                ingestion_log=ingestion_log,
                ingestion_type=ingestion_type,
                project_type=project_type,
                status="success",
                records_processed=records_processed,
                records_written=records_written,
                records_failed=0,
                records_skipped=records_skipped,
                nested_records_fetched=None,
                failed_record_ids=None,
                skipped_record_ids=skipped_record_ids,
                error_message=None,
            )

        except Exception as e:

            # if the entire project-type ingestion throws an exception,
            # mark the log row as failed
            finish_ingestion_log(
                db_path=bronze_path,
                ingestion_log=ingestion_log,
                run_id=run_id,
                ingestion_type=ingestion_type,
                project_type=project_type,
                status="failed",
                error_message=str(e),
            )

            print(
                f"\t(ERROR) Failed to ingest "
                f"project_type {project_type}: {e}"
            )

            # continue processing the remaining project types
            continue


    with duckdb.connect(
        bronze_path,
        read_only=True,
    ) as bronze_con:

        current_run_log = bronze_con.execute(
            f"""
            SELECT *
            FROM {ingestion_log}
            WHERE run_id = ?
            AND ingestion_type = ?
            ORDER BY project_type
            """,
            [
                run_id,
                ingestion_type,
            ],
        ).fetchdf()


    if current_run_log.empty:
        raise ValueError(
            "Ingestion log is empty for the current run."
        )


    failed_rows = current_run_log[
        current_run_log["status"].str.lower() == "failed"
    ]


    if not failed_rows.empty:

        print(
            "Current ingestion results:"
        )

        print(
            current_run_log.to_string(
                index=False
            )
        )

        raise ValueError(
            "One or more project types failed ingestion."
        )

if __name__ == "__main__":
    args = parse_args()
    
    asyncio.run(ingestion(
        env=args.env
    ))