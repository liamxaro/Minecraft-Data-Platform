import json
import polars as pl
import yaml


def parse_payload(payload) -> dict:
    if isinstance(payload, str):
        return json.loads(payload)

    return payload


def model(dbt, session):
    dbt.config(
        materialized="incremental",
        incremental_strategy="merge",
        unique_key=[
            "project_type",
            "project_id",
        ],
        on_schema_change="append_new_columns",
        merge_update_condition=(
            "DBT_INTERNAL_SOURCE.hashed_payload "
            "<> DBT_INTERNAL_DEST.hashed_payload"
        ),
    )

    if dbt.is_incremental:
        incremental_cte = f"""
            processed_watermarks AS (
                SELECT
                    project_type,
                    MAX(c_pull_timestamp_utc) AS max_pull_timestamp

                FROM {dbt.this}

                GROUP BY
                    project_type
            ),
        """

        incremental_join = """
            LEFT JOIN processed_watermarks AS w
                ON r.project_type = w.project_type
        """

        incremental_filter = """
            AND (
                w.max_pull_timestamp IS NULL
                OR r.c_pull_timestamp_utc > w.max_pull_timestamp
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
                project_type

            FROM bronze.main.ingestion_log

            WHERE status = 'success'
        ),

        candidate_rows AS (
            SELECT
                r.run_id,
                r.project_type,
                r.project_id,
                r.payload,
                r.hashed_payload,
                r.c_pull_timestamp_utc

            FROM bronze.main.modrinth_project_listings AS r

            INNER JOIN successful_runs AS s
                ON r.run_id = s.run_id
                AND r.project_type = s.project_type

            {incremental_join}

            WHERE 1 = 1
            {incremental_filter}
        ),

        latest_project_state AS (
            SELECT
                run_id,
                project_type,
                project_id,
                payload,
                hashed_payload,
                c_pull_timestamp_utc,

                ROW_NUMBER() OVER (
                    PARTITION BY
                        project_type,
                        project_id

                    ORDER BY
                        c_pull_timestamp_utc DESC,
                        run_id DESC
                ) AS rn

            FROM candidate_rows
        )

        SELECT
            run_id,
            project_type,
            project_id,
            payload,
            hashed_payload,
            c_pull_timestamp_utc

        FROM latest_project_state

        WHERE rn = 1
    """

    raw_df = session.sql(query).pl()

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
            "No successful Bronze project listing rows were found."
        )

    metadata_df = raw_df.drop(
        "payload"
    )

    payload_rows = [
        parse_payload(payload)
        for payload in raw_df["payload"].to_list()
    ]

    payload_df = pl.from_dicts(
        payload_rows,
        infer_schema_length=None,
    )

    duplicate_columns = list(
        set(metadata_df.columns)
        & set(payload_df.columns)
    )

    if duplicate_columns:
        payload_df = payload_df.drop(
            duplicate_columns
        )

    return metadata_df.hstack(
        payload_df
    )