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

    bronze_path = os.path.join(
        project_root,
        "data",
        "bronze",
        target,
        "api_modrinth_com.duckdb",
    )

    silver_path = os.path.join(
        project_root,
        "data",
        "silver",
        target,
        "api_modrinth_com.duckdb",
    )

    os.makedirs(
        os.path.dirname(silver_path),
        exist_ok=True,
    )

    dbt_env = os.environ.copy()

    dbt_env["DBT_BRONZE_PATH"] = bronze_path
    dbt_env["DBT_SILVER_PATH"] = silver_path
    dbt_env["DBT_MEMORY_LIMIT"] = "14GB"
    dbt_env["DBT_THREADS"] = "1"

    command = [
        str(dbt_path),
        "run",
        "--project-dir",
        transformations_dir,
        "--profiles-dir",
        transformations_dir,
        "--target",
        target,
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
        f"(INFO) Python executable: {sys.executable}"
    )

    print(
        f"(INFO) dbt executable: {dbt_path}"
    )

    print(
        f"(INFO) Bronze: {bronze_path}"
    )

    print(
        f"(INFO) Silver: {silver_path}"
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
        select=args.select,
        full_refresh=args.full_refresh,
    )