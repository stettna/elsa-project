
from pathlib import Path
import argparse


def create_run_directories(parent_dir: str, new_dir_name: str):
    """
    Create a directory with three run subdirectories.
    Each run directory contains eval-results, run-info, and trajectories.
    """
    base_dir = Path(parent_dir) / new_dir_name

    # Create the main directory
    base_dir.mkdir(parents=True, exist_ok=True)

    # Create the run directories and their subdirectories
    for i in range(1, 4):
        run_dir = base_dir / f"run-{i}"
        run_dir.mkdir(exist_ok=True)

        for subdir in ["eval-info", "run-info", "trajectories"]:
            (run_dir / subdir).mkdir(exist_ok=True)

    print(f"Directory structure created at: {base_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Create a directory structure for three runs."
    )
    parser.add_argument("parent_dir", help="Path to the parent directory")
    parser.add_argument("new_dir_name", help="Name of the new directory")

    args = parser.parse_args()

    create_run_directories(args.parent_dir, args.new_dir_name)
