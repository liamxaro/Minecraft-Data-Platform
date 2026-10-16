import argparse
import os
import subprocess
import sys
from pathlib import Path


project_root = (
    Path(__file__)
    .resolve()
    .parents[3]
)

transformations_dir = (
    project_root
    / "transformations"
)


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
        default="path:models/gold/modrinth",
    )

    parser.add_argument(
        "--full-refresh",
        action="store_true",
    )

    return parser.parse_args()


def run_dbt(
    target: str,
    select: str = "path:models/gold/modrinth",
    full_refresh: bool = False,
) -> None:
    dbt_executable = (
        Path(sys.executable).parent
        / "dbt"
    )

    if not dbt_executable.exists():
        raise RuntimeError(
            f"dbt executable was not found at: "
            f"{dbt_executable}"
        )

    database_file_name = (
        "api_modrinth_com.duckdb"
    )

    bronze_path = (
        project_root
        / "data"
        / "bronze"
        / target
        / database_file_name
    )

    silver_path = (
        project_root
        / "data"
        / "silver"
        / target
        / database_file_name
    )

    gold_path = (
        project_root
        / "data"
        / "gold"
        / target
        / database_file_name
    )

    if not bronze_path.exists():
        raise FileNotFoundError(
            f"Bronze database was not found: "
            f"{bronze_path}"
        )

    if not silver_path.exists():
        raise FileNotFoundError(
            f"Silver database was not found: "
            f"{silver_path}"
        )

    gold_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dbt_env = os.environ.copy()

    dbt_env["DBT_BRONZE_PATH"] = str(
        bronze_path
    )

    dbt_env["DBT_SILVER_PATH"] = str(
        silver_path
    )

    dbt_env["DBT_GOLD_PATH"] = str(
        gold_path
    )

    dbt_env["DBT_MEMORY_LIMIT"] = "14GB"
    dbt_env["DBT_THREADS"] = "1"

    dbt_target = (
        f"{target}_gold"
    )

    command = [
        str(dbt_executable),
        "run",
        "--project-dir",
        str(transformations_dir),
        "--profiles-dir",
        str(transformations_dir),
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
        "(INFO) Layer: gold"
    )

    print(
        f"(INFO) dbt target: {dbt_target}"
    )

    print(
        f"(INFO) Selection: {select}"
    )

    print(
        f"(INFO) Full refresh: {full_refresh}"
    )

    print(
        f"(INFO) Python executable: "
        f"{sys.executable}"
    )

    print(
        f"(INFO) dbt executable: "
        f"{dbt_executable}"
    )

    print(
        f"(INFO) Bronze database: "
        f"{bronze_path}"
    )

    print(
        f"(INFO) Silver database: "
        f"{silver_path}"
    )

    print(
        f"(INFO) Gold database: "
        f"{gold_path}"
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