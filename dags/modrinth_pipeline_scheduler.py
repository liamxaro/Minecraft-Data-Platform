from pathlib import Path

import pendulum

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator


# -------------------------------------------------------------------
# PROJECT PATHS
# -------------------------------------------------------------------

project_root = Path(__file__).resolve().parents[1]

pipeline_venv = project_root / ".venv"

jupyter_executable = (
    pipeline_venv
    / "bin"
    / "jupyter"
)


# -------------------------------------------------------------------
# MODRINTH GENERAL PATHS
# -------------------------------------------------------------------

general_pipeline_root = (
    project_root
    / "pipelines"
    / "modrinth_api_general"
)

general_notebook_directory = (
    general_pipeline_root
    / "notebooks"
)

general_bronze_notebook = (
    general_notebook_directory
    / "modrinth-general-ingestion.ipynb"
)

general_silver_notebook = (
    general_notebook_directory
    / "modrinth-general-bronze-to-silver.ipynb"
)


# -------------------------------------------------------------------
# MODRINTH DETAIL PATHS
# -------------------------------------------------------------------

detail_pipeline_root = (
    project_root
    / "pipelines"
    / "modrinth_api_detail"
)

detail_notebook_directory = (
    detail_pipeline_root
    / "notebooks"
)

detail_bronze_notebook = (
    detail_notebook_directory
    / "modrinth-detail-ingestion.ipynb"
)

detail_silver_notebook = (
    detail_notebook_directory
    / "modrinth-detail-bronze-to-silver.ipynb"
)


# -------------------------------------------------------------------
# DAG
# -------------------------------------------------------------------

with DAG(
    dag_id="modrinth_pipeline",
    description=(
        "Modrinth General and Detail pipelines "
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

    tags=[
        "modrinth",
        "general",
        "detail",
    ],
) as dag:


    # -------------------------------------------------------------------
    # GENERAL BRONZE
    # -------------------------------------------------------------------

    bronze_project_listings = BashOperator(
        task_id="bronze_project_listings",

        bash_command=f"""
            set -e

            cd "{general_notebook_directory}"

            "{jupyter_executable}" nbconvert \
                --to notebook \
                --execute "{general_bronze_notebook.name}" \
                --output-dir "/tmp" \
                --output "modrinth-general-ingestion-output.ipynb" \
                --ExecutePreprocessor.timeout=-1
        """,
    )


    # -------------------------------------------------------------------
    # GENERAL SILVER
    # -------------------------------------------------------------------

    silver_project_listings = BashOperator(
        task_id="silver_project_listings",

        bash_command=f"""
            set -e

            cd "{general_notebook_directory}"

            "{jupyter_executable}" nbconvert \
                --to notebook \
                --execute "{general_silver_notebook.name}" \
                --output-dir "/tmp" \
                --output "modrinth-general-bronze-to-silver-output.ipynb" \
                --ExecutePreprocessor.timeout=-1
        """,
    )


    # -------------------------------------------------------------------
    # DETAIL BRONZE
    # -------------------------------------------------------------------

    bronze_project_details = BashOperator(
        task_id="bronze_project_details",

        bash_command=f"""
            set -e

            cd "{detail_notebook_directory}"

            "{jupyter_executable}" nbconvert \
                --to notebook \
                --execute "{detail_bronze_notebook.name}" \
                --output-dir "/tmp" \
                --output "modrinth-detail-ingestion-output.ipynb" \
                --ExecutePreprocessor.timeout=-1
        """,
    )


    # -------------------------------------------------------------------
    # DETAIL SILVER
    # -------------------------------------------------------------------

    silver_project_details = BashOperator(
        task_id="silver_project_details",

        bash_command=f"""
            set -e

            cd "{detail_notebook_directory}"

            "{jupyter_executable}" nbconvert \
                --to notebook \
                --execute "{detail_silver_notebook.name}" \
                --output-dir "/tmp" \
                --output "modrinth-detail-bronze-to-silver-output.ipynb" \
                --ExecutePreprocessor.timeout=-1
        """,
    )


    # -------------------------------------------------------------------
    # DEPENDENCIES
    # -------------------------------------------------------------------

    (
        bronze_project_listings
        >> silver_project_listings
        >> bronze_project_details
        >> silver_project_details
    )