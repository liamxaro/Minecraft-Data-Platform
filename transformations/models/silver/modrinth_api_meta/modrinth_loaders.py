import json

import polars as pl


def model(dbt, session):
    dbt.config(
        materialized="table",
        tags=["modrinth_meta"],
    )

    raw_df = session.sql(
        """
        SELECT
            b.run_id,
            b.payload,
            b.hashed_payload,
            b.c_pull_timestamp_utc

        FROM bronze.main.modrinth_loaders AS b

        INNER JOIN bronze.main.ingestion_log_sync AS l
            ON b.run_id = l.run_id
            AND b.stream = l.stream

        WHERE b.stream = 'loaders'
          AND LOWER(TRIM(l.status)) = 'success'

        ORDER BY
            b.c_pull_timestamp_utc DESC,
            b.run_id DESC

        LIMIT 1
        """
    ).pl()

    if raw_df.is_empty():
        raise RuntimeError(
            "No successful Bronze snapshot found for loaders."
        )

    payload = raw_df["payload"][0]

    if isinstance(payload, str):
        payload = json.loads(payload)

    silver_df = pl.from_dicts(
        payload,
        infer_schema_length=None,
    )

    return silver_df.with_columns(
        pl.lit(
            raw_df["run_id"][0]
        ).alias("run_id"),

        pl.lit(
            raw_df["hashed_payload"][0]
        ).alias("hashed_payload"),

        pl.lit(
            raw_df["c_pull_timestamp_utc"][0]
        ).alias("c_pull_timestamp_utc"),
    )