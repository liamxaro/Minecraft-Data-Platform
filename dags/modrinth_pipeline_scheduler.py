from pathlib import Path

import pendulum

from airflow.sdk import DAG, Param
from airflow.providers.standard.operators.bash import BashOperator


# -------------------------------------------------------------------
# PROJECT PATHS
# -------------------------------------------------------------------

project_root = Path(__file__).resolve().parents[1]

pipeline_venv = (
    project_root
    / ".venv"
)

python_executable = (
    pipeline_venv
    / "bin"
    / "python"
)


# -------------------------------------------------------------------
# MODRINTH META PATHS
# -------------------------------------------------------------------

meta_pipeline_root = (
    project_root
    / "pipelines"
    / "modrinth_api_meta"
)

meta_src_directory = (
    meta_pipeline_root
    / "src"
)

meta_bronze_script = (
    meta_src_directory
    / "modrinth_meta_ingestion.py"
)

meta_silver_script = (
    meta_src_directory
    / "bronze_to_silver.py"
)


# -------------------------------------------------------------------
# MODRINTH GENERAL PATHS
# -------------------------------------------------------------------

general_pipeline_root = (
    project_root
    / "pipelines"
    / "modrinth_api_general"
)

general_src_directory = (
    general_pipeline_root
    / "src"
)

general_bronze_script = (
    general_src_directory
    / "modrinth_general_ingestion.py"
)

general_silver_script = (
    general_src_directory
    / "bronze_to_silver_dbt.py"
)


# -------------------------------------------------------------------
# MODRINTH DETAIL PATHS
# -------------------------------------------------------------------

detail_pipeline_root = (
    project_root
    / "pipelines"
    / "modrinth_api_detail"
)

detail_src_directory = (
    detail_pipeline_root
    / "src"
)

detail_bronze_script = (
    detail_src_directory
    / "modrinth_detail_ingestion.py"
)

detail_silver_script = (
    detail_src_directory
    / "bronze_to_silver_dbt.py"
)


# -------------------------------------------------------------------
# DAG
# -------------------------------------------------------------------

with DAG(
    dag_id="modrinth_pipeline",

    description=(
        "Modrinth Meta, General, and Detail pipelines "
        "from Bronze through Silver."
    ),

    start_date=pendulum.datetime(
        2026,
        8,
        25,
        0,
        0,
        tz="America/Los_Angeles",
    ),

    schedule="@once",

    catchup=False,
    max_active_runs=1,

    params={
        "environment": Param(
            default="dev",
            type="string",
            enum=[
                "dev",
                "test",
                "prod",
            ],
        ),

        "search_page_concurrency": Param(
            default=8,
            type="integer",
            minimum=1,
            maximum=20,
        ),

        "dbt_full_refresh": Param(
            default=False,
            type="boolean",
        ),
    },

    tags=[
        "modrinth",
        "meta",
        "general",
        "detail",
    ],
) as dag:


    # -------------------------------------------------------------------
    # META BRONZE
    # -------------------------------------------------------------------

    bronze_meta = BashOperator(
        task_id="modrinth_api_meta_ingestion",

        bash_command=f"""
            set -euo pipefail

            "{python_executable}" \
                "{meta_bronze_script}" \
                --env "$PIPELINE_ENV"
        """,

        env={
            "PIPELINE_ENV": "{{ params.environment }}",
        },

        append_env=True,
        cwd=str(project_root),
    )


    # -------------------------------------------------------------------
    # META SILVER
    # -------------------------------------------------------------------

    silver_meta = BashOperator(
        task_id="modrinth_api_meta_dbt",

        bash_command=f"""
            set -euo pipefail

            command=(
                "{python_executable}"
                "{meta_silver_script}"
                --target "$PIPELINE_ENV"
                --select "tag:modrinth_meta"
            )

            case "${{DBT_FULL_REFRESH:-false}}" in
                true|True|TRUE|1)
                    command+=(--full-refresh)
                    ;;
            esac

            "${{command[@]}}"
        """,

        env={
            "PIPELINE_ENV": "{{ params.environment }}",
            "DBT_FULL_REFRESH": "{{ params.dbt_full_refresh }}",
        },

        append_env=True,
        cwd=str(project_root),
    )


    # -------------------------------------------------------------------
    # GENERAL BRONZE
    # -------------------------------------------------------------------

    bronze_project_listings = BashOperator(
        task_id="modrinth_api_general_ingestion",

        bash_command=f"""
            set -euo pipefail

            "{python_executable}" \
                "{general_bronze_script}" \
                --env "$PIPELINE_ENV" \
                --search-page-concurrency "$SEARCH_PAGE_CONCURRENCY"
        """,

        env={
            "PIPELINE_ENV": "{{ params.environment }}",
            "SEARCH_PAGE_CONCURRENCY": (
                "{{ params.search_page_concurrency }}"
            ),
        },

        append_env=True,
        cwd=str(project_root),
    )


    # -------------------------------------------------------------------
    # GENERAL SILVER
    # -------------------------------------------------------------------

    silver_project_listings = BashOperator(
        task_id="modrinth_api_general_dbt",

        bash_command=f"""
            set -euo pipefail

            command=(
                "{python_executable}"
                "{general_silver_script}"
                --target "$PIPELINE_ENV"
                --select "modrinth_project_listings"
            )

            case "${{DBT_FULL_REFRESH:-false}}" in
                true|True|TRUE|1)
                    command+=(--full-refresh)
                    ;;
            esac

            "${{command[@]}}"
        """,

        env={
            "PIPELINE_ENV": "{{ params.environment }}",
            "DBT_FULL_REFRESH": "{{ params.dbt_full_refresh }}",
        },

        append_env=True,
        cwd=str(project_root),
    )


    # -------------------------------------------------------------------
    # DETAIL BRONZE
    # -------------------------------------------------------------------

    bronze_project_details = BashOperator(
        task_id="modrinth_api_detail_ingestion",

        bash_command=f"""
            set -euo pipefail

            "{python_executable}" \
                "{detail_bronze_script}" \
                --env "$PIPELINE_ENV"
        """,

        env={
            "PIPELINE_ENV": "{{ params.environment }}",
        },

        append_env=True,
        cwd=str(project_root),
    )


    # -------------------------------------------------------------------
    # DETAIL SILVER
    # -------------------------------------------------------------------

    silver_project_details = BashOperator(
        task_id="modrinth_api_detail_dbt",

        bash_command=f"""
            set -euo pipefail

            command=(
                "{python_executable}"
                "{detail_silver_script}"
                --target "$PIPELINE_ENV"
                --select "modrinth_project_versions"
            )

            case "${{DBT_FULL_REFRESH:-false}}" in
                true|True|TRUE|1)
                    command+=(--full-refresh)
                    ;;
            esac

            "${{command[@]}}"
        """,

        env={
            "PIPELINE_ENV": "{{ params.environment }}",
            "DBT_FULL_REFRESH": "{{ params.dbt_full_refresh }}",
        },

        append_env=True,
        cwd=str(project_root),
    )


    # -------------------------------------------------------------------
    # DEPENDENCIES
    # -------------------------------------------------------------------

    (
        bronze_meta
        >> silver_meta
        >> bronze_project_listings
        >> silver_project_listings
        >> bronze_project_details
        >> silver_project_details
    )