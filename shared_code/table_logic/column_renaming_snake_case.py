import re
import polars as pl


def to_snake_case(column_name: str) -> str:
    column_name = re.sub(
        r"([A-Z]+)([A-Z][a-z])",
        r"\1_\2",
        column_name,
    )

    column_name = re.sub(
        r"([a-z0-9])([A-Z])",
        r"\1_\2",
        column_name,
    )

    column_name = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        column_name,
    )

    return (
        column_name
        .strip("_")
        .lower()
    )


def convert_columns_to_snake_case(
    df: pl.DataFrame,
) -> pl.DataFrame:

    column_mapping = {
        column: to_snake_case(column)
        for column in df.columns
    }

    normalized_columns = list(
        column_mapping.values()
    )

    if len(normalized_columns) != len(
        set(normalized_columns)
    ):
        raise ValueError(
            "Snake case conversion produced "
            "duplicate column names."
        )

    return df.rename(
        column_mapping
    )