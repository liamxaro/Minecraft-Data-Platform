def build_bronze_modrinth_project_listings_schema(
    table_name: str,
) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            run_id VARCHAR NOT NULL,
            project_type VARCHAR NOT NULL,
            project_id VARCHAR NOT NULL,
            payload JSON NOT NULL,
            hashed_payload VARCHAR NOT NULL,
            c_pull_timestamp_utc TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (
                run_id,
                project_type,
                project_id
            )
        );
    """


def build_ingestion_log_schema(
    table_name: str,
) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            run_id VARCHAR NOT NULL,
            ingestion_type VARCHAR NOT NULL,
            api_url VARCHAR NOT NULL,
            project_type VARCHAR NOT NULL,
            status VARCHAR NOT NULL,

            records_processed BIGINT,
            records_written BIGINT,
            records_failed BIGINT,
            records_skipped BIGINT,
            nested_records_fetched BIGINT,

            failed_record_ids VARCHAR[],
            skipped_record_ids VARCHAR[],

            error_message VARCHAR,
            start_time TIMESTAMPTZ,
            end_time TIMESTAMPTZ,
            duration_seconds DOUBLE,

            PRIMARY KEY (
                run_id,
                ingestion_type,
                project_type
            )
        );
    """