import duckdb


def init_db(
    db_path: str,
    schemas: list[str] | None = None,
) -> None:
    """
    Initialize a DuckDB database and optionally create tables.

    Args:
        db_path: Absolute path to the DuckDB database.
        schemas: Optional CREATE TABLE statements to execute.
    """

    with duckdb.connect(db_path) as db_con:
        if schemas:
            for schema in schemas:
                db_con.execute(schema)