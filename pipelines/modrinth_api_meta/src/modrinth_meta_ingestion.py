import yaml
import requests
import json
import duckdb
import os
import argparse
import uuid
from datetime import datetime, timezone

from shared_code.database.directory_creation import *
from shared_code.database.database_and_schema_creation import *
from pipelines.modrinth_api_meta.schemas.modrinth_meta_schemas import *

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

    return parser.parse_args()

def write_ingestion_log(
    con,
    table_name: str,
    run_id: str,
    stream: str,
    request: str,
    response: str,
    row_count: int,
    watermark: datetime,
    status: str,
) -> None:

    con.execute(
        f"""
        INSERT INTO {table_name}
        (
            run_id,
            stream,
            request,
            response,
            row_count,
            watermark,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            run_id,
            stream,
            request,
            response,
            str(row_count),
            watermark.isoformat(),
            status,
        ],
    )

def ingest(env: str):
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

    with open(os.path.join(pipeline_dir, "stream-config.yml"), "r") as file:
        config = yaml.safe_load(file)


    main_config = config.get("main", {})
    streams = config.get("streams", [])

    env = 'dev'
    headers = main_config.get("headers", {})
    data_dir = main_config.get("parent-folder", "data")
    ingestion_log = main_config.get("ingestion-log", "ingestion_log")

    bronze_db_path = os.path.join(project_root, data_dir, 'bronze', env, build_db_filename(streams[0]['source-url']))
    build_layer_directory(os.path.dirname(bronze_db_path))

    bronze_schemas = [build_bronze_modrinth_meta_schemas(stream['table-name']) for stream in streams] + [build_ingestion_log_schema(ingestion_log)]
    init_db(bronze_db_path, bronze_schemas)


    with duckdb.connect(bronze_db_path) as bronze_con:

        run_id = str(uuid.uuid4())

        for idx, stream in enumerate(streams):

            if "source-url" not in stream:
                continue

            stream_name = stream["name"]
            url = stream["source-url"]
            table_name = stream["table-name"]

            print(
                f"{idx + 1}/{len(streams)} "
                f"Ingesting data from {url}"
            )

            pull_timestamp = datetime.now(timezone.utc)

            try:
                response = requests.get(
                    url,
                    headers=headers,
                    timeout=30,
                )

                response.raise_for_status()

                data = response.json()

                print("\t(INFO) Received data")

                payload = json.dumps(
                    data,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )

                bronze_con.execute(
                    f"""
                    INSERT INTO {table_name}
                    (
                        run_id,
                        stream,
                        payload,
                        hashed_payload,
                        c_pull_timestamp_utc
                    )

                    SELECT
                        ?,
                        ?,
                        CAST(? AS JSON),
                        md5(?),
                        ?
                    """,
                    [
                        run_id,
                        stream_name,
                        payload,
                        payload,
                        pull_timestamp,
                    ],
                )

                row_count = (
                    len(data)
                    if isinstance(data, list)
                    else 1
                )

                print(
                    f"\t(INFO) Wrote {row_count:,} "
                    f"records to {table_name}"
                )

            except requests.RequestException as e:
                print(
                    f"\t(ERROR) Failed fetching "
                    f"data from {url}: {e}"
                )


                continue

if __name__ == "__main__":
    
    args = parse_args()
    
    ingest(args.env)


