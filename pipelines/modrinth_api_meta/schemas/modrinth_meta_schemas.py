def build_bronze_modrinth_meta_schemas(
    table_name: str,
) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            run_id VARCHAR NOT NULL,
            stream VARCHAR NOT NULL,
            payload JSON NOT NULL,
            hashed_payload VARCHAR NOT NULL,
            c_pull_timestamp_utc TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (
                run_id,
                stream
            )
        );
    """
    
def build_ingestion_log_schema(
    table_name: str,
) -> str:
    return f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            run_id VARCHAR NOT NULL,
            stream VARCHAR NOT NULL,
            request VARCHAR NOT NULL,
            response VARCHAR NOT NULL,
            row_count VARCHAR NOT NULL,
            watermark VARCHAR NOT NULL,
            status VARCHAR NOT NULL,

            PRIMARY KEY (
                run_id,
                stream
            )
        );
    """