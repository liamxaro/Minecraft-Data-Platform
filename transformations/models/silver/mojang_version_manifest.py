import hashlib
import json

import polars as pl


BRONZE_TABLE = "bronze.main.mojang_version_manifest"
INGESTION_LOG_TABLE = "bronze.main.ingestion_log"
INGESTION_TYPE = "mojang_version_manifest"


def parse_payload(payload) -> dict:
    if isinstance(payload, str):
        return json.loads(payload)

    return payload


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


def flatten_manifest_metadata(payload: dict) -> dict:
    metadata = {}

    for key, value in payload.items():
        if key == "versions":
            continue

        if isinstance(value, dict):
            for nested_key, nested_value in value.items():
                metadata[f"{key}_{nested_key}"] = nested_value
        else:
            metadata[key] = value

    return metadata


def build_silver_rows(raw_df: pl.DataFrame) -> list[dict]:
    silver_rows = []

    for row in raw_df.iter_rows(named=True):
        payload = parse_payload(
            row["payload"]
        )

        versions = payload.get(
            "versions",
            [],
        )

        if not isinstance(versions, list):
            raise TypeError(
                "Expected Mojang manifest 'versions' to be a list."
            )

        manifest_metadata = flatten_manifest_metadata(
            payload
        )

        for version in versions:
            if not isinstance(version, dict):
                continue

            version_id = version.get("id")

            if not version_id:
                continue

            version_payload = {
                key: value
                for key, value in version.items()
                if key != "id"
            }

            silver_row = {
                "run_id": row["run_id"],
                "stream": row["stream"],
                "version_id": version_id,
                "hashed_payload": hash_payload(version),
                "c_pull_timestamp_utc": row[
                    "c_pull_timestamp_utc"
                ],
                **manifest_metadata,
                **version_payload,
            }

            silver_rows.append(
                silver_row
            )

    return silver_rows


def model(dbt, session):
    dbt.config(
        materialized="incremental",
        incremental_strategy="merge",
        unique_key=[
            "stream",
            "version_id",
        ],
        on_schema_change="append_new_columns",
        merge_update_condition=(
            "DBT_INTERNAL_SOURCE.c_pull_timestamp_utc "
            "> DBT_INTERNAL_DEST.c_pull_timestamp_utc"
        ),
    )

    if dbt.is_incremental:
        incremental_cte = f"""
            processed_watermarks AS (
                SELECT
                    stream,
                    MAX(
                        c_pull_timestamp_utc
                    ) AS max_pull_timestamp

                FROM {dbt.this}

                GROUP BY
                    stream
            ),
        """

        incremental_join = """
            LEFT JOIN processed_watermarks AS w
                ON r.stream = w.stream
        """

        incremental_filter = """
            AND (
                w.max_pull_timestamp IS NULL
                OR r.c_pull_timestamp_utc
                    > w.max_pull_timestamp
            )
        """

    else:
        incremental_cte = ""
        incremental_join = ""
        incremental_filter = ""

    query = f"""
        WITH
        {incremental_cte}

        successful_runs AS (
            SELECT DISTINCT
                run_id,
                project_type AS stream

            FROM {INGESTION_LOG_TABLE}

            WHERE status = 'success'
                AND ingestion_type = '{INGESTION_TYPE}'
        ),

        candidate_snapshots AS (
            SELECT
                r.run_id,
                r.stream,
                r.payload,
                r.c_pull_timestamp_utc

            FROM {BRONZE_TABLE} AS r

            INNER JOIN successful_runs AS s
                ON r.run_id = s.run_id
                AND r.stream = s.stream

            {incremental_join}

            WHERE 1 = 1

            {incremental_filter}
        ),

        latest_stream_snapshot AS (
            SELECT
                run_id,
                stream,
                payload,
                c_pull_timestamp_utc

            FROM (
                SELECT
                    run_id,
                    stream,
                    payload,
                    c_pull_timestamp_utc,

                    ROW_NUMBER() OVER (
                        PARTITION BY
                            stream

                        ORDER BY
                            c_pull_timestamp_utc DESC,
                            run_id DESC
                    ) AS rn

                FROM candidate_snapshots
            )

            WHERE rn = 1
        )

        SELECT
            run_id,
            stream,
            payload,
            c_pull_timestamp_utc

        FROM latest_stream_snapshot
    """

    raw_df = session.sql(
        query
    ).pl()

    if raw_df.height == 0:
        if dbt.is_incremental:
            return session.sql(
                f"""
                SELECT *
                FROM {dbt.this}
                WHERE FALSE
                """
            )

        raise RuntimeError(
            "No successful Bronze Mojang version manifest "
            "rows were found."
        )

    silver_rows = build_silver_rows(
        raw_df
    )

    if not silver_rows:
        if dbt.is_incremental:
            return session.sql(
                f"""
                SELECT *
                FROM {dbt.this}
                WHERE FALSE
                """
            )

        raise RuntimeError(
            "The Mojang version manifest contained no versions."
        )

    silver_df = pl.from_dicts(
        silver_rows,
        infer_schema_length=None,
        strict=False,
    )

    null_columns = [
        column_name
        for column_name, data_type in zip(
            silver_df.columns,
            silver_df.dtypes,
        )
        if data_type == pl.Null
    ]

    if null_columns:
        silver_df = silver_df.drop(
            null_columns
        )

    return silver_df