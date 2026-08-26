from pathlib import Path

import pendulum

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator


# -------------------------------------------------------------------
# PATHS
# -------------------------------------------------------------------

project_root = Path(__file__).resolve().parents[1]

pipeline_root = (
    project_root
    / "pipelines"
    / "mojang_version_manifest"
)

notebook_directory = pipeline_root / "notebooks"

pipeline_venv = project_root / ".venv"

jupyter_executable = (
    pipeline_venv
    / "bin"
    / "jupyter"
)

bronze_notebook = (
    notebook_directory
    / "mojang-version-manifest-ingestion.ipynb"
)

silver_notebook = (
    notebook_directory
    / "mojang-version-manifest-bronze-to-silver.ipynb"
)


# -------------------------------------------------------------------
# DAG
# -------------------------------------------------------------------

with DAG(
    dag_id="mojang_version_manifest",
    description="Mojang version manifest ingestion and Bronze-to-Silver pipeline.",

    # Midnight tonight:
    # August 26, 2026 @ 12:00 AM Los Angeles time
    start_date=pendulum.datetime(
        2026,
        8,
        25,
        0,
        0,
        tz="America/Los_Angeles",
    ),

    # Run once
    schedule="@once",

    catchup=False,
    max_active_runs=1,

    tags=[
        "mojang",
        "version_manifest",
    ],
) as dag:

    bronze_version_manifest = BashOperator(
        task_id="bronze_version_manifest",
        bash_command=f"""
            set -e

            cd "{notebook_directory}"

            "{jupyter_executable}" nbconvert \
                --to notebook \
                --execute "{bronze_notebook.name}" \
                --output-dir "/tmp" \
                --output "mojang-version-manifest-ingestion-output.ipynb" \
                --ExecutePreprocessor.timeout=-1
        """,
    )

    silver_version_manifest = BashOperator(
        task_id="silver_version_manifest",
        bash_command=f"""
            set -e

            cd "{notebook_directory}"

            "{jupyter_executable}" nbconvert \
                --to notebook \
                --execute "{silver_notebook.name}" \
                --output-dir "/tmp" \
                --output "mojang-version-manifest-bronze-to-silver-output.ipynb" \
                --ExecutePreprocessor.timeout=-1
        """,
    )


    # Bronze must finish successfully before Silver begins.
    bronze_version_manifest >> silver_version_manifest