import duckdb
import yaml
import os
import requests
import uuid
import json
from datetime import datetime, timezone
import argparse
import hashlib

from shared_code.database.directory_creation import *
from shared_code.database.database_and_schema_creation import *
from pipelines.mojang_version_manifest.schemas.mojang_schemas import *

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
    
    return parser.parse_args()

def hash_payload(payload: dict) -> str:
    canonical_payload = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical_payload.encode("utf-8")
    ).hexdigest()

def get_official_minecraft_versions(url: str, headers: dict) -> dict | None:

    print(f"\t (INFO) Attempting to connect to: {url}")
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        payload = response.json()

    except Exception as e:
        print(f"\t(ERROR) Error occurred processing request: {e}")
        return None

    return payload


def start_ingestion_log(
    db_con: duckdb.DuckDBPyConnection,
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

    db_con.execute(
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
    db_con: duckdb.DuckDBPyConnection,
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

    db_con.execute(
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


def ingest_mojang_version_manifest(env: str):
    """
    Ingests Mojang version manifest data from the official Mojang API
    and stores it in a DuckDB database.
    """

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

    config_path = os.path.join(
        pipeline_dir,
        "stream-config.yml",
    )

    with open(config_path, "r") as file:
        config_data = yaml.safe_load(file)

    config = config_data.get("main", {})
    streams = config_data.get("streams", [])
    headers = config.get("headers", {})
    ingestion_log = config.get(
        "ingestion-log",
        "",
    )

    if not streams:
        raise ValueError(
            "No streams were defined in stream-config.yml."
        )

    file_name = build_db_filename(
        streams[0]["source-url"]
    )

    table_name = streams[0]["table-name"]

    bronze_path = os.path.join(
        project_root,
        config["parent-folder"],
        "bronze",
        env,
        file_name,
    )

    build_layer_directory(
        os.path.dirname(bronze_path)
    )

    bronze_schemas = [
        build_bronze_mojang_version_manifest_schema(
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

    run_id = str(uuid.uuid4())
    ingestion_type = "mojang_version_manifest"

    with duckdb.connect(bronze_path) as bronze_con:

        for idx, stream in enumerate(streams):

            table_name = stream["table-name"]
            source_url = stream["source-url"]
            stream_name = stream["name"]

            print(
                f"{idx + 1}/{len(streams)} "
                f"Ingesting stream: {stream_name}"
            )

            start_ingestion_log(
                db_con=bronze_con,
                ingestion_log=ingestion_log,
                source_url=source_url,
                run_id=run_id,
                ingestion_type=ingestion_type,
                project_type=stream_name,
            )

            try:
                payload = get_official_minecraft_versions(
                    url=source_url,
                    headers=headers,
                )

                if not payload:
                    raise ValueError(
                        f"Empty payload returned from {source_url}"
                    )

                print(
                    "\t (INFO): Data retrieved"
                )

                pull_timestamp_utc = datetime.now(
                    timezone.utc
                )

                payload_json = json.dumps(
                    payload
                )

                hashed_payload = hash_payload(
                    payload
                )

                insert_sql = f"""
                    INSERT INTO {table_name}
                    (
                        run_id,
                        stream,
                        payload,
                        hashed_payload,
                        c_pull_timestamp_utc
                    )
                    VALUES (?, ?, ?, ?, ?)
                """

                bronze_con.execute(
                    insert_sql,
                    (
                        run_id,
                        stream_name,
                        payload_json,
                        hashed_payload,
                        pull_timestamp_utc,
                    ),
                )

                nested_records_fetched = len(
                    payload.get(
                        "versions",
                        [],
                    )
                )

                finish_ingestion_log(
                    db_con=bronze_con,
                    ingestion_log=ingestion_log,
                    run_id=run_id,
                    ingestion_type=ingestion_type,
                    project_type=stream_name,
                    status="success",
                    records_processed=1,
                    records_written=1,
                    records_failed=0,
                    records_skipped=0,
                    nested_records_fetched=(
                        nested_records_fetched
                    ),
                )

                print(
                    "\t (SUCCESS): Data successfully "
                    "retrieved and written to:"
                    f"\n\t\t{bronze_path}"
                )

            except Exception as exc:

                finish_ingestion_log(
                    db_con=bronze_con,
                    ingestion_log=ingestion_log,
                    run_id=run_id,
                    ingestion_type=ingestion_type,
                    project_type=stream_name,
                    status="failed",
                    records_processed=1,
                    records_written=0,
                    records_failed=1,
                    records_skipped=0,
                    nested_records_fetched=0,
                    error_message=str(exc),
                )

                print(
                    f"\t (ERROR): Failed to ingest "
                    f"{stream_name}: {exc}"
                )

                raise


if __name__ == "__main__":
    args = parse_args()

    ingest_mojang_version_manifest(
        env=args.env
    )