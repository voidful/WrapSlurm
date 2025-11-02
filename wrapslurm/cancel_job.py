"""Simple wrapper around scancel for cancelling SLURM jobs."""

import argparse
import subprocess
import sys
from typing import List


def cancel_jobs(job_ids: List[str], signal: str = None, user: str = None) -> int:
    """Cancel one or more SLURM jobs using scancel."""
    if not job_ids:
        print("Error: At least one job ID must be provided.")
        return 1

    base_cmd = ["scancel"]
    if signal:
        base_cmd.extend(["--signal", signal])
    if user:
        base_cmd.extend(["--user", user])

    exit_code = 0
    for job_id in job_ids:
        cmd = base_cmd + [job_id]
        try:
            subprocess.run(cmd, check=True)
            print(f"Cancelled job {job_id}")
        except FileNotFoundError:
            print("Error: 'scancel' command not found. Ensure SLURM client tools are installed.")
            return 1
        except subprocess.CalledProcessError as exc:
            print(f"Failed to cancel job {job_id}: {exc}")
            exit_code = exc.returncode or 1
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cancel SLURM jobs with a friendly wrapper around scancel.",
    )
    parser.add_argument(
        "job_ids",
        nargs="+",
        help="One or more SLURM job IDs to cancel.",
    )
    parser.add_argument(
        "--signal",
        help="Optional signal to send to the job (passed to scancel).",
    )
    parser.add_argument(
        "--user",
        help="Cancel jobs for a specific user (passed to scancel).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    exit_code = cancel_jobs(args.job_ids, signal=args.signal, user=args.user)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
