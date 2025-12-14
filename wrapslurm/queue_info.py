import subprocess
import getpass
import grp
from terminaltables import AsciiTable
from termcolor import colored
import os
import sys
import re

MAX_NAME_LENGTH = 30  # Maximum length for the job name


def truncate_name(name, max_length):
    """
    Truncate the job name if it exceeds the maximum length.
    Append '...' to indicate truncation.
    """
    if len(name) > max_length:
        return name[:max_length - 3] + "..."
    return name


def run_command(cmd, shell=False):
    """Run a shell command and return its output."""
    try:
        if shell:
            output = subprocess.check_output(cmd, stderr=subprocess.PIPE, shell=True, text=True)
        else:
            output = subprocess.check_output(cmd, stderr=subprocess.PIPE, text=True)
        return output.strip()
    except subprocess.CalledProcessError:
        return ""
    except Exception:
        return ""


def get_job_gpu_req(job_id):
    """Parse scontrol to find GPU requirements for a job."""
    output = run_command(["scontrol", "show", "job", str(job_id)])
    # Look for ReqTRES=...gres/gpu=N...
    req_tres = re.search(r"ReqTRES=.*gres/gpu(?::[a-zA-Z0-9]+)?=(\d+)", output)
    if req_tres:
        return int(req_tres.group(1))
    
    # Look for TresPerJob=...gres/gpu:N...
    tres_per_job = re.search(r"TresPerJob=.*gres/gpu(?::[a-zA-Z0-9]+)?:(\d+)", output)
    if tres_per_job:
        return int(tres_per_job.group(1))
        
    return 0


def get_user_gpu_running(user):
    """Calculate total GPUs currently running for a user."""
    # Get all running job IDs for the user
    output = run_command(["squeue", "-u", user, "-t", "R", "-h", "-o", "%i"])
    if not output:
        return 0
    
    total_gpu = 0
    job_ids = output.split()
    for jid in job_ids:
        total_gpu += get_job_gpu_req(jid)
    
    return total_gpu


def get_user_pending_jobs(user):
    """Get list of pending job IDs for a user."""
    output = run_command(["squeue", "-u", user, "-t", "PD", "-h", "-o", "%i"])
    if not output:
        return []
    return output.split()


def analyze_pending_job_brief(job_id, user):
    """
    Display a brief analysis panel for a pending job.
    Shows key information in a compact table format.
    """
    from terminaltables import AsciiTable
    
    # Get job details from squeue
    squeue_out = run_command(["squeue", "-j", str(job_id), "-h", "-o", "%i|%P|%j|%T|%M|%l|%D|%R"])
    if not squeue_out:
        print(colored(f"  Job {job_id}: Not found in queue", "red"))
        return
    
    parts = squeue_out.split('|')
    if len(parts) < 8:
        print(colored(f"  Job {job_id}: Unable to parse job info", "red"))
        return
    
    partition = parts[1].strip()
    job_name = truncate_name(parts[2].strip(), MAX_NAME_LENGTH)
    state = parts[3].strip()
    wait_time = parts[4].strip()
    time_limit = parts[5].strip()
    nodes = parts[6].strip()
    reason = parts[7].strip()
    
    # Get GPU requirements
    gpu_req = get_job_gpu_req(job_id)
    
    # Get scontrol details for more info
    scontrol_out = run_command(["scontrol", "show", "job", str(job_id)])
    
    # Parse CPUs per task
    cpus_match = re.search(r"NumCPUs=(\d+)", scontrol_out)
    cpus = cpus_match.group(1) if cpus_match else "N/A"
    
    # Parse memory
    mem_match = re.search(r"MinMemoryNode=(\d+\w?)", scontrol_out)
    memory = mem_match.group(1) if mem_match else "N/A"
    
    # Build the panel rows
    rows = [
        ["Setting", "Value"],
        ["Job ID", colored(str(job_id), "yellow", attrs=["bold"])],
        ["Name", job_name],
        ["Partition", partition],
        ["Nodes", nodes],
        ["CPUs", cpus],
        ["Memory", memory],
        ["GPUs", str(gpu_req) if gpu_req > 0 else "0"],
        ["Time Limit", time_limit],
        ["Wait Time", wait_time],
        ["Reason", colored(reason, "red" if "QOSMAXGRES" in reason.upper() or "PRIORITY" in reason.upper() else "yellow")],
    ]
    
    # Create table
    table = AsciiTable(rows)
    table.title = colored(f" Job {job_id} ", "cyan", attrs=["bold"])
    table.justify_columns[0] = 'right'
    table.justify_columns[1] = 'left'
    print(table.table)
    
    # Additional analysis for specific reasons
    reason_upper = reason.upper()
    
    if "QOSMAXGRESPERUSER" in reason_upper:
        user_gpu_running = get_user_gpu_running(user)
        total_if_run = user_gpu_running + gpu_req
        print(colored("  ⚠ GPU Limit Exceeded:", "red", attrs=["bold"]))
        print(f"    Running GPUs: {colored(str(user_gpu_running), 'green')} | "
              f"This job needs: {colored(str(gpu_req), 'yellow')} | "
              f"Total if started: {colored(str(total_if_run), 'red')}")
    elif "PRIORITY" in reason_upper:
        print(colored("  ℹ Waiting for higher priority jobs to complete", "cyan"))
    elif "RESOURCES" in reason_upper:
        print(colored("  ℹ Waiting for resources (CPU/GPU/Memory) to become available", "cyan"))
    elif "PARTITION" in reason_upper:
        print(colored("  ℹ Partition constraints - check partition availability", "cyan"))


def analyze_job(job_id):
    """
    Analyze a specific job ID and print detailed status.
    Translates the logic from the provided bash script.
    """
    print(colored(f"Job ID: {job_id}", "cyan", attrs=["bold"]))
    print(colored("=" * 20, "cyan"))
    print()

    # 1. Check status from squeue
    print(colored("[1] Current status from squeue", "yellow"))
    print("-" * 20)

    squeue_out = run_command(["squeue", "-j", str(job_id), "-h", "-o", "%i %t %T %M %R"])

    if not squeue_out:
        print(colored("Job not found in squeue. It may be completed, failed, or purged from queue.", "red"))
        print(colored("Trying sacct for historical info...", "yellow"))
        print()
        
        # sacct fallback
        sacct_cmd = ["sacct", "-j", str(job_id), "--format=JobIDRaw,State,Elapsed,Timelimit,AllocCPUS,NodeList,ExitCode,Reason", "-P"]
        sacct_out = run_command(sacct_cmd)
        if sacct_out:
             # Pretty print sacct output (replace | with spacing)
             header = sacct_out.split('\n')[0].replace('|', '  ')
             print(colored(header, attrs=['bold']))
             for line in sacct_out.split('\n')[1:]:
                 print(line.replace('|', '  '))
        else:
            print("No info found in sacct.")
        return

    parts = squeue_out.split()
    # squeue output format: JobID StateShort StateLong Time Reason/Node
    # Caution: Reason can contain spaces? Usually %R is last, so remainder is reason.
    # But split() might break it. Let's rely on fixed fields if possible or careful split.
    # The bash script uses awk column logic.
    # %i %t %T %M %R
    # jobid st ST time reason
    
    job_state_short = parts[1]
    job_state_long = parts[2]
    job_time = parts[3]
    job_reason = " ".join(parts[4:])

    print(f"  State(short): {colored(job_state_short, attrs=['bold'])}")
    print(f"  State(long) : {colored(job_state_long, attrs=['bold'])}")
    print(f"  Time        : {job_time}")
    print(f"  Reason/Node : {job_reason}")
    print()

    # 2. Analyze based on state
    print(colored(f"[2] Analysis", "yellow"))
    print("-" * 20)

    if job_state_short == "R":
        print("Job is RUNNING.")
        print("Showing more details from scontrol:")
        print(run_command(["scontrol", "show", "job", str(job_id)]))

    elif job_state_short == "PD":
        print(colored("Job is PENDING.", "yellow"))
        print(f"Reason: {job_reason}")
        print()
        
        reason_upper = job_reason.upper()
        
        reasons_map = {
            "PRIORITY": "Lower priority. Waiting for higher priority jobs to finish.",
            "RESOURCES": "Insufficient resources (CPU/GPU/Mem or Node constraints).",
            "PARTITION": "Partition constraints (down or time limit mismatch).",
            "ACCT_MAX_CPU_PER_USER": "Account reached CPU usage limit.",
            "QOS": "QOS limit reached.",
            "NODE_DOWN": "Required node(s) are down or in maintenance.",
            "LICENSE": "Waiting for licenses.",
            "ASSOCIATION": "Association limit reached."
        }

        found_reason = False
        for key, explanation in reasons_map.items():
            if key in reason_upper:
                print(f"- {colored(key, 'red')}: {explanation}")
                found_reason = True
        
        # Special handling for QOSMaxGRESPerUser
        if "QOSMAXGRESPERUSER" in reason_upper:
            print()
            print(colored("!!! QOSMaxGRESPerUser Detected !!!", "red", attrs=["bold"]))
            print("This QOS has a limit on GPU per user.")
            print("Starting this job would exceed your total GPU limit.")
            print()

            # Get User ID from scontrol
            scontrol_out = run_command(["scontrol", "show", "job", str(job_id)])
            user_match = re.search(r"UserId=([a-z0-9_]+)", scontrol_out)
            job_user = user_match.group(1) if user_match else "unknown"

            job_gpu_req = get_job_gpu_req(job_id)
            user_gpu_running = get_user_gpu_running(job_user)
            total_if_run = user_gpu_running + job_gpu_req

            print(f"  User: {colored(job_user, attrs=['bold'])}")
            print(f"  Current RUNNING GPUs: {colored(str(user_gpu_running), 'green')}")
            print(f"  This Job Requires:    {colored(str(job_gpu_req), 'yellow')}")
            print(f"  Total if Started:     {colored(str(total_if_run), 'red')}")
            print()
            print(f"  The limit L satisfies: {user_gpu_running} <= L < {total_if_run}")
            print()
            
            # Try sacctmgr for exact limit
            try:
                # Mocking check for sacctmgr existence by running it
                sacctmgr_out = run_command(["sacctmgr", "show", "qos", "-nP", "format=Name,MaxTRESPerUser"])
                # Output format: Name|MaxTRESPerUser
                # We need to find the relevant line. Since we don't know which QOS, we might look for any that has GPU limit?
                # The bash script just grep gpu.
                # Let's try to extract any gpu limit
                if sacctmgr_out:
                    gpu_limits = re.findall(r"gres/gpu=(\d+)", sacctmgr_out)
                    if gpu_limits:
                        limit_gpu = int(gpu_limits[0]) # Start with the first one found, better than nothing
                        over_by = total_if_run - limit_gpu
                        print(colored("  [sacctmgr Estimate]", "cyan"))
                        print(f"  Found a QOS with MaxTRESPerUser: gres/gpu={limit_gpu}")
                        if over_by > 0:
                            print(f"  You would exceed this limit by {over_by} GPUs.")
                        else:
                            print("  (Warning: The active QOS might be different from this detected one.)")
            except Exception:
                pass
        
        if not found_reason and "QOSMAXGRESPERUSER" not in reason_upper:
             print("Please check 'scontrol show job' for more details.")
             print(run_command(["scontrol", "show", "job", str(job_id)]))

    elif job_state_short == "CG":
        print("Job is COMPLETING.")
        sacct_cmd = ["sacct", "-j", str(job_id), "--format=JobIDRaw,State,Elapsed,Timelimit,AllocCPUS,NodeList,ExitCode,Reason", "-P"]
        print(run_command(sacct_cmd).replace('|', '  '))

    elif job_state_short in ["F", "TO", "NF", "CA", "CD", "FAILED", "TIMEOUT", "NODE_FAIL", "CANCELLED", "COMPLETED"]:
        print(f"Job is in terminal state: {job_state_short}")
        sacct_cmd = ["sacct", "-j", str(job_id), "--format=JobIDRaw,State,Elapsed,Timelimit,AllocCPUS,NodeList,ExitCode,Reason", "-P"]
        print(run_command(sacct_cmd).replace('|', '  '))
        
    else:
        print(f"Job state: {job_state_short}")
        print(run_command(["scontrol", "show", "job", str(job_id)]))

    print()
    print(colored("=" * 20, "cyan"))


def show_squeue():
    """
    Display the output of the `squeue` command in a prettier, tabular format.
    Includes truncating overly long job names and highlighting user jobs.
    """
    # Get the current user's information and group memberships
    try:
        user = getpass.getuser()
        gid = max(os.getgroups())
        gr_mem = grp.getgrgid(gid).gr_mem
    except Exception as e:
        # Fallback if group info fails
        user = os.environ.get('USER', 'unknown')
        gr_mem = []

    # Execute the `squeue` command and format the output for parsing
    cmd = ['squeue', '--noheader', '-o', '%i|%P|%j|%u|%T|%M|%D|%R']
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.PIPE, text=True).strip()
    except FileNotFoundError:
        print("Command 'squeue' not found. Please ensure SLURM is installed and added to PATH.")
        return
    except subprocess.CalledProcessError as e:
        print(f"Error while executing squeue: {e.stderr.strip()}")
        return
    except Exception as e:
        print(f"Unexpected error while executing squeue: {e}")
        return

    # Parse the output into lines
    lines = output.split('\n')
    if not lines or len(lines) == 1 and not lines[0].strip():
        print("No jobs in the queue.")
        return

    # Define table headers
    titles = ["JobID", "Partition", "Name", "User", "State", "Time", "Nodes", "NodeList"]

    # Parse each line and build rows for the table
    rows = []
    for line in lines:
        parts = line.split('|')
        if len(parts) < 8:
            continue  # Skip incomplete lines

        job_id = parts[0].strip()
        partition = parts[1].strip()
        job_name = truncate_name(parts[2].strip(), MAX_NAME_LENGTH)
        username = parts[3].strip()
        state = parts[4].strip()
        run_time = parts[5].strip()
        node_count = parts[6].strip()
        nodelist = parts[7].strip()

        # Highlight jobs belonging to the current user or user's group
        mygroup = (username == user or username in gr_mem)
        if mygroup:
            username = colored(username, 'yellow', attrs=['bold'])
            job_id = colored(job_id, 'yellow', attrs=['bold'])
        else:
            job_id = colored(job_id, 'white', attrs=['bold'])

        # Color job states based on their value
        state_lower = state.lower()
        if 'r' in state_lower:  # Running
            state = colored(state, 'green', attrs=['bold'])
        elif 'pd' in state_lower:  # Pending
            state = colored(state, 'yellow', attrs=['bold'])
        elif 'cg' in state_lower:  # Completing
            state = colored(state, 'blue', attrs=['bold'])
        elif 'f' in state_lower or 'fail' in state_lower:  # Failed
            state = colored(state, 'red', attrs=['bold'])
        else:  # Other states
            state = colored(state, 'cyan', attrs=['bold'])

        # Add the row to the table
        row = [job_id, partition, job_name, username, state, run_time, node_count, nodelist]
        rows.append(row)

    # Create and print the table
    table = AsciiTable([titles] + rows)
    for i in range(len(titles)):
        table.justify_columns[i] = 'left'
    table.justify_columns[0] = 'right'  # Right-align JobID for better readability
    print(table.table)

    # Automatically analyze the current user's pending jobs
    pending_jobs = get_user_pending_jobs(user)
    if pending_jobs:
        print()
        print(colored("=" * 60, "cyan"))
        print(colored(f"  Your Pending Jobs Analysis ({len(pending_jobs)} job(s))", "cyan", attrs=["bold"]))
        print(colored("=" * 60, "cyan"))
        for job_id in pending_jobs:
            print()
            analyze_pending_job_brief(job_id, user)


def main():
    """
    Main entry point for the `wqueue` command.
    """
    try:
        if len(sys.argv) > 1 and sys.argv[1] not in ["-h", "--help"]:
            analyze_job(sys.argv[1])
        else:
            show_squeue()
    except KeyboardInterrupt:
        pass
    except RuntimeError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
