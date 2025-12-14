import os
import glob
import subprocess
import argparse
import getpass

try:
    import questionary
    from questionary import Style
    QUESTIONARY_AVAILABLE = True
except ImportError:
    QUESTIONARY_AVAILABLE = False

# Custom style for the interactive prompts
CUSTOM_STYLE = None
if QUESTIONARY_AVAILABLE:
    CUSTOM_STYLE = Style([
        ("qmark", "fg:cyan bold"),
        ("question", "fg:white bold"),
        ("answer", "fg:green bold"),
        ("pointer", "fg:cyan bold"),
        ("highlighted", "fg:cyan bold"),
        ("selected", "fg:green"),
    ])


def get_running_job_ids():
    """
    Get list of running job IDs for the current user from squeue.
    """
    try:
        user = getpass.getuser()
        output = subprocess.check_output(
            ["squeue", "-u", user, "-t", "R", "-h", "-o", "%i|%j"],
            stderr=subprocess.PIPE,
            text=True
        ).strip()
        if not output:
            return []
        
        jobs = []
        for line in output.split('\n'):
            if '|' in line:
                parts = line.split('|')
                job_id = parts[0].strip()
                job_name = parts[1].strip() if len(parts) > 1 else ""
                jobs.append((job_id, job_name))
        return jobs
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []


def find_logs_matching_id(job_id, report_dir="./slurm-report"):
    """
    Find log files that contain the given job_id in their filename.
    Uses partial matching instead of exact filename match.
    """
    try:
        # Get all log files in the directory
        log_files = glob.glob(os.path.join(report_dir, "*.out"))
        if not log_files:
            return []
        
        # Filter logs that contain the job_id in their filename
        matching = [f for f in log_files if job_id in os.path.basename(f)]
        
        # Sort by modification time (newest first)
        matching.sort(key=os.path.getmtime, reverse=True)
        return matching
    except Exception:
        return []


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


def select_log_interactive(running_jobs, report_dir="./slurm-report"):
    """
    Show an interactive selection menu for running job logs.
    """
    if not QUESTIONARY_AVAILABLE:
        print("Multiple running jobs found. Please specify a job ID.")
        for job_id, job_name in running_jobs:
            print(f"  {job_id}: {job_name}")
        exit(1)
    
    # Build choices with job info and check if log exists
    choices = []
    for job_id, job_name in running_jobs:
        log_file = os.path.join(report_dir, f"{job_id}.out")
        log_exists = os.path.exists(log_file)
        
        # Also check for partial matches
        if not log_exists:
            matching_logs = find_logs_matching_id(job_id, report_dir)
            log_exists = len(matching_logs) > 0
        
        status = "✓" if log_exists else "✗"
        label = f"{status} {job_id}: {job_name[:40]}" if job_name else f"{status} {job_id}"
        choices.append(questionary.Choice(title=label, value=job_id))
    
    # Add option for latest log
    choices.append(questionary.Choice(title="📄 Latest log file", value="__latest__"))
    
    result = questionary.select(
        "Select a running job to view its log:",
        choices=choices,
        style=CUSTOM_STYLE,
    ).ask()
    
    if result is None:
        print("Cancelled.")
        exit(0)
    
    return result


def watch_log(log_file):
    """
    Follow the specified log file using ``tail -f``.
    """
    try:
        print(f"Watching log file: {log_file}")
        subprocess.run(["tail", "-n", "20", "-f", log_file])
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
        # Search for logs containing the job ID (partial match)
        matching_logs = find_logs_matching_id(args.job_id, args.report_dir)
        
        if not matching_logs:
            print(f"Error: No log file containing ID '{args.job_id}' found in {args.report_dir}")
            exit(1)
        elif len(matching_logs) == 1:
            log_file = matching_logs[0]
        else:
            # Multiple matches, let user select
            if QUESTIONARY_AVAILABLE:
                choices = [questionary.Choice(title=os.path.basename(f), value=f) for f in matching_logs]
                log_file = questionary.select(
                    f"Multiple logs match '{args.job_id}'. Select one:",
                    choices=choices,
                    style=CUSTOM_STYLE,
                ).ask()
                if log_file is None:
                    print("Cancelled.")
                    exit(0)
            else:
                # Without questionary, use the most recent one
                print(f"Multiple logs match '{args.job_id}', using most recent: {os.path.basename(matching_logs[0])}")
                log_file = matching_logs[0]
    else:
        # No job_id specified, check for running jobs
        running_jobs = get_running_job_ids()
        
        if len(running_jobs) > 1:
            # Multiple running jobs, show interactive selection
            selected_id = select_log_interactive(running_jobs, args.report_dir)
            
            if selected_id == "__latest__":
                log_file = find_latest_log(report_dir=args.report_dir)
            else:
                # Find log for selected job (with partial matching)
                matching_logs = find_logs_matching_id(selected_id, args.report_dir)
                if matching_logs:
                    log_file = matching_logs[0]
                else:
                    # Try exact match as fallback
                    log_file = os.path.join(args.report_dir, f"{selected_id}.out")
                    if not os.path.exists(log_file):
                        print(f"Error: Log file for job ID {selected_id} not found in {args.report_dir}")
                        exit(1)
        else:
            # Zero or one running job, use latest log
            log_file = find_latest_log(report_dir=args.report_dir)

    # Watch the log file
    watch_log(log_file)

