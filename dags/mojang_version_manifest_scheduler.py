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
# MOJANG VERSION MANIFEST PATHS
# -------------------------------------------------------------------

pipeline_root = (
    project_root
    / "pipelines"
    / "mojang_version_manifest"
)

src_directory = (
    pipeline_root
    / "src"
)

bronze_script = (
    src_directory
    / "mojang_version_manifest_ingestion.py"
)

silver_script = (
    src_directory
    / "bronze_to_silver_dbt.py"
)


# -------------------------------------------------------------------
# DAG
# -------------------------------------------------------------------

with DAG(
    dag_id="mojang_version_manifest",

    description=(
        "Mojang version manifest pipeline "
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

        "dbt_full_refresh": Param(
            default=False,
            type="boolean",
        ),
    },

    tags=[
        "mojang",
        "version_manifest",
    ],
) as dag:


    # -------------------------------------------------------------------
    # BRONZE
    # -------------------------------------------------------------------

    bronze_version_manifest = BashOperator(
        task_id="bronze_version_manifest",

        bash_command=f"""
            set -euo pipefail

            "{python_executable}" \
                "{bronze_script}" \
                --env "$PIPELINE_ENV"
        """,

        env={
            "PIPELINE_ENV": "{{ params.environment }}",
        },

        append_env=True,
        cwd=str(project_root),
    )


    # -------------------------------------------------------------------
    # SILVER
    # -------------------------------------------------------------------

    silver_version_manifest = BashOperator(
        task_id="silver_version_manifest",

        bash_command=f"""
            set -euo pipefail

            command=(
                "{python_executable}"
                "{silver_script}"
                --target "$PIPELINE_ENV"
                --select "mojang_version_manifest"
            )

            if [[ "${{DBT_FULL_REFRESH,,}}" == "true" ]]; then
                command+=(--full-refresh)
            fi

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

    bronze_version_manifest >> silver_version_manifest