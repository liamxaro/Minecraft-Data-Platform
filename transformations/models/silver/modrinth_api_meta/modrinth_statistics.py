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

        FROM bronze.main.modrinth_statistics AS b

        INNER JOIN bronze.main.ingestion_log_sync AS l
            ON b.run_id = l.run_id
            AND b.stream = l.stream

        WHERE b.stream = 'statistics'
          AND LOWER(TRIM(l.status)) = 'success'

        ORDER BY
            b.c_pull_timestamp_utc,
            b.run_id
        """
    ).pl()

    if raw_df.is_empty():
        raise RuntimeError(
            "No successful Bronze snapshots found for statistics."
        )

    rows = []

    for row in raw_df.iter_rows(
        named=True
    ):
        payload = row["payload"]

        if isinstance(payload, str):
            payload = json.loads(payload)

        payload["run_id"] = row["run_id"]
        payload["hashed_payload"] = row["hashed_payload"]
        payload["c_pull_timestamp_utc"] = (
            row["c_pull_timestamp_utc"]
        )

        rows.append(payload)

    return pl.from_dicts(
        rows,
        infer_schema_length=None,
    )