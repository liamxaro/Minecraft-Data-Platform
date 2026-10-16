import argparse
import os
import subprocess
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--target",
        choices=[
            "dev",
            "test",
            "prod",
        ],
        default="dev",
    )

    parser.add_argument(
        "--layer",
        choices=[
            "silver",
            "gold",
        ],
        default="silver",
    )

    parser.add_argument(
        "--select",
        required=True,
    )

    parser.add_argument(
        "--full-refresh",
        action="store_true",
    )

    return parser.parse_args()


def run_dbt(
    target: str,
    layer: str,
    select: str,
    full_refresh: bool = False,
) -> None:
    src_dir = os.path.dirname(
        os.path.abspath(__file__)
    )

    project_root = os.path.abspath(
        os.path.join(
            src_dir,
            "..",
            "..",
            "..",
        )
    )

    transformations_dir = os.path.join(
        project_root,
        "transformations",
    )

    dbt_path = (
        Path(sys.executable).parent
        / "dbt"
    )

    if not dbt_path.exists():
        raise RuntimeError(
            f"dbt executable was not found at: "
            f"{dbt_path}"
        )

    database_file_name = (
        "api_modrinth_com.duckdb"
    )

    bronze_path = os.path.join(
        project_root,
        "data",
        "bronze",
        target,
        database_file_name,
    )

    silver_path = os.path.join(
        project_root,
        "data",
        "silver",
        target,
        database_file_name,
    )

    gold_path = os.path.join(
        project_root,
        "data",
        "gold",
        target,
        database_file_name,
    )

    if layer == "silver":
        output_path = silver_path

    elif layer == "gold":
        output_path = gold_path

    else:
        raise ValueError(
            f"Unsupported layer: {layer}"
        )

    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True,
    )

    dbt_env = os.environ.copy()

    dbt_env["DBT_BRONZE_PATH"] = bronze_path
    dbt_env["DBT_SILVER_PATH"] = silver_path
    dbt_env["DBT_GOLD_PATH"] = gold_path
    dbt_env["DBT_MEMORY_LIMIT"] = "14GB"
    dbt_env["DBT_THREADS"] = "1"

    dbt_target = (
        f"{target}_{layer}"
    )

    command = [
        str(dbt_path),
        "run",
        "--project-dir",
        transformations_dir,
        "--profiles-dir",
        transformations_dir,
        "--target",
        dbt_target,
        "--select",
        select,
    ]

    if full_refresh:
        command.append(
            "--full-refresh"
        )

    print(
        f"(INFO) Environment: {target}"
    )

    print(
        f"(INFO) Layer: {layer}"
    )

    print(
        f"(INFO) dbt target: {dbt_target}"
    )

    print(
        f"(INFO) Python executable: "
        f"{sys.executable}"
    )

    print(
        f"(INFO) dbt executable: "
        f"{dbt_path}"
    )

    print(
        f"(INFO) Bronze: "
        f"{bronze_path}"
    )

    print(
        f"(INFO) Silver: "
        f"{silver_path}"
    )

    print(
        f"(INFO) Gold: "
        f"{gold_path}"
    )

    print(
        f"(INFO) Output database: "
        f"{output_path}"
    )

    print(
        f"(INFO) DuckDB memory limit: "
        f"{dbt_env['DBT_MEMORY_LIMIT']}"
    )

    print(
        f"(INFO) dbt threads: "
        f"{dbt_env['DBT_THREADS']}"
    )

    subprocess.run(
        command,
        cwd=project_root,
        env=dbt_env,
        check=True,
    )


if __name__ == "__main__":
    args = parse_args()

    run_dbt(
        target=args.target,
        layer=args.layer,
        select=args.select,
        full_refresh=args.full_refresh,
    )