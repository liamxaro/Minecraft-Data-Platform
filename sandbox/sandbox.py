from pathlib import Path
import shutil
import subprocess


project_root = Path(__file__).resolve().parents[2]
transformations_dir = project_root / "transformations"
print(transformations_dir)