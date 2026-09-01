import argparse
import os
import shutil
import subprocess


project_root = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "../../..",
    )
)

src_dir = os.path.dirname(
        os.path.abspath(__file__)
    )

pipeline_dir = os.path.abspath(
        os.path.join(
            src_dir,
            "..",
        )
    )

transformations_dir = os.path.join(
    project_root,
    "transformations",
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
        default=None,
    )

    parser.add_argument(
        "--full-refresh",
        action="store_true",
    )

    return parser.parse_args()

def run_dbt(
    target: str,
    select: str | None = None,
    full_refresh: bool = False,
) -> None:
    dbt_executable = shutil.which("dbt")

    if dbt_executable is None:
        raise RuntimeError(
            "dbt executable was not found "
            "in the current environment."
        )

    command = [
        dbt_executable,
        "run",
        "--project-dir",
        transformations_dir,
        "--profiles-dir",
        transformations_dir,
        "--target",
        target,
    ]

    if select:
        command.extend(
            [
                "--select",
                select,
            ]
        )

    if full_refresh:
        command.append(
            "--full-refresh"
        )

    subprocess.run(
        command,
        cwd=project_root,
        check=True,
    )


if __name__ == "__main__":
    args = parse_args()

    run_dbt(
        target=args.target,
        select=args.select,
        full_refresh=args.full_refresh,
    )