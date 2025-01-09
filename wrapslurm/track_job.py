import os
import glob
import subprocess
import argparse


def find_latest_log(report_dir="./slurm-report"):
    """
    Find the latest log file in the specified directory.
    """
    try:
        # Get a list of all log files in the directory
        log_files = glob.glob(os.path.join(report_dir, "*.out"))
        if not log_files:
            raise FileNotFoundError(f"No log files found in {report_dir}")

        # Sort by modification time and return the latest
        latest_log = max(log_files, key=os.path.getmtime)
        return latest_log
    except FileNotFoundError as e:
        print(f"Error: {e}")
        exit(1)


def watch_log(log_file):
    """
    Watch the specified log file using `watch` and `tail`.
    """
    try:
        print(f"Watching log file: {log_file}")
        subprocess.run(["watch", "tail", "-n", "20", log_file])
    except KeyboardInterrupt:
        print("\nStopped watching log.")
    except Exception as e:
        print(f"Error: {e}")
        exit(1)


def main():
    """
    Main entry point for the `wlog` command.
    """
    parser = argparse.ArgumentParser(description="Watch SLURM log files in real-time.")
    parser.add_argument("job_id", nargs="?", help="SLURM job ID to watch the log file for (optional, defaults to the latest log)")
    parser.add_argument("--report-dir", default="./slurm-report", help="Directory containing SLURM log files (default: ./slurm-report)")
    args = parser.parse_args()

    if args.job_id:
        # Construct the log file path for the specific job ID
        log_file = os.path.join(args.report_dir, f"{args.job_id}-slurm.out")
        if not os.path.exists(log_file):
            print(f"Error: Log file for job ID {args.job_id} not found in {args.report_dir}")
            exit(1)
    else:
        # Find the latest log file
        log_file = find_latest_log(report_dir=args.report_dir)

    # Watch the log file
    watch_log(log_file)

