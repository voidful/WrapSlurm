#!/usr/bin/env python3
"""
wrun.py

This script handles both interactive (bash) sessions and non-interactive jobs on a SLURM cluster.
- If the command is "bash" or the user specifies --interactive, it will run "srun" directly with CPU/GPU/memory/time configurations.
- Otherwise, it will generate an sbatch script and submit it with "sbatch".
"""

import argparse
import os
import subprocess
from datetime import datetime

DEFAULT_SLURM_TEMPLATE = """#!/bin/bash
#SBATCH -N {nodes}                            # Number of nodes
#SBATCH -p {partition}                        # Partition
#SBATCH --account={account}                   # Account name
#SBATCH --ntasks-per-node={tasks_per_node}    # Tasks per node
#SBATCH --cpus-per-task={cpus_per_task}       # CPU cores per task
#SBATCH --mem={memory}                        # Memory per node
#SBATCH --gres=gpu:{gpus}                     # Number of GPUs per node
#SBATCH --time={time}                         # Maximum job time (e.g., 4-00:00:00)
#SBATCH -o ./Report/%j-slurm.out              # Output log file
{nodelist_option}{exclude_option}

# Logging SLURM environment variables
echo "SLURM_NNODES=${{SLURM_NNODES}}"
echo "NODELIST=${{SLURM_JOB_NODELIST}}"
echo "SLURM_NODEID=${{SLURM_NODEID}}"
echo "SLURM_ARRAY_TASK_ID=${{SLURM_ARRAY_TASK_ID}}"

# Set master node and port for distributed training
export MASTER_ADDR=$(scontrol show hostnames ${{SLURM_JOB_NODELIST}} | head -n 1)
export MASTER_PORT=$(shuf -i 1024-65535 -n 1)

# Enable error handling and debugging for NCCL and CUDA
export TORCH_NCCL_ASYNC_ERROR_HANDLING=1
export CUDA_LAUNCH_BLOCKING=1
export TORCH_DISTRIBUTED_DEBUG=DETAIL

# Execute the training script directly (non-interactive)
CMD="{command}"
srun --wait=60 --kill-on-bad-exit=1 --mpi=pmix bash -c "$CMD"
"""


def get_default_account():
    """
    Retrieve the default SLURM account for the current user by querying sacctmgr.
    If no account is found or the command fails, raise an exception.
    """
    try:
        cmd = [
            "sacctmgr",
            "show",
            "assoc",
            f"user={os.getenv('USER')}",
            "format=Account",
            "--noheader",
        ]
        result = subprocess.check_output(cmd, text=True)
        lines = [line.strip() for line in result.strip().split("\n") if line.strip()]
        if lines:
            return lines[0]
        else:
            raise RuntimeError("No default account found for the user.")
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip() if e.stderr else "No error output found."
        raise RuntimeError(f"Error querying account: {err_msg}")
    except FileNotFoundError:
        raise RuntimeError("Command 'sacctmgr' not found. Please ensure SLURM is installed and in PATH.")


def get_node_resources():
    """
    Query SLURM for available resources via sinfo.
    Return default values for partition, nodes, cpus_per_task, memory, and gpus.
    """
    try:
        result = subprocess.check_output(["sinfo", "--format=%P|%N|%C|%m", "--noheader"], text=True).strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error executing sinfo: {e.stderr.strip()}")
    except FileNotFoundError:
        raise RuntimeError("Command 'sinfo' not found. Please ensure SLURM is installed and in PATH.")

    best_partition = None
    best_nodes = 1
    best_cpus_per_task = 1
    best_memory = "50G"
    best_gpus = 1

    # Parse sinfo output line by line
    for line in result.split("\n"):
        parts = line.split("|")
        if len(parts) < 4:
            continue
        partition, nodes, cpu_info, memory = parts[:4]
        # Clean up partition in case there's a trailing asterisk or other symbols
        partition = partition.split("*")[0].strip()
        cpus_total = int(cpu_info.split("/")[-1].strip())
        memory_clean = "".join(filter(str.isdigit, memory))  # Extract digits from memory string
        memory_val = int(memory_clean) if memory_clean else 0  # Memory in MB

        if not best_partition or cpus_total > best_cpus_per_task:
            best_partition = partition
            best_nodes = 1
            best_cpus_per_task = cpus_total
            # Convert memory from MB to GB, fallback is 50G if not found
            best_memory = f"{memory_val // 1024}G" if memory_val > 0 else "50G"

    return best_partition, best_nodes, best_cpus_per_task, best_memory, best_gpus


def generate_sbatch_script(args):
    """
    Generate an sbatch script based on the provided arguments (non-interactive mode).
    """
    # Auto-detect resources if not explicitly specified
    if args.partition is None or args.nodes is None or args.cpus_per_task is None or args.memory is None:
        best_partition, best_nodes, best_cpus_per_task, best_memory, best_gpus = get_node_resources()
        args.partition = args.partition or best_partition
        args.nodes = args.nodes or best_nodes
        args.cpus_per_task = args.cpus_per_task or best_cpus_per_task
        args.memory = args.memory or best_memory
        args.gpus = args.gpus or best_gpus

    # Auto-detect account if not specified
    args.account = args.account or get_default_account()

    # Prepare node-specific options
    nodelist_option = f"#SBATCH --nodelist={args.nodelist}\n" if args.nodelist else ""
    exclude_option = f"#SBATCH --exclude={args.exclude}\n" if args.exclude else ""

    # Build the sbatch script from the template
    sbatch_script = DEFAULT_SLURM_TEMPLATE.format(
        nodes=args.nodes,
        partition=args.partition,
        account=args.account,
        tasks_per_node=args.tasks_per_node,
        cpus_per_task=args.cpus_per_task,
        memory=args.memory,
        gpus=args.gpus,
        time=args.time,
        nodelist_option=nodelist_option,
        exclude_option=exclude_option,
        command=args.command,
    )

    # Determine the script file name based on current timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_name = f"job_{timestamp}.sbatch"
    script_path = os.path.join(os.getcwd(), script_name)

    # Write the sbatch script to disk
    with open(script_path, "w") as f:
        f.write(sbatch_script)

    print(f"Generated sbatch script: {script_path}")
    return script_path


def submit_sbatch(script_path):
    """
    Submit the generated sbatch script using the sbatch command and provide a hint for monitoring logs.
    """
    # Ensure 'Report' directory exists
    report_dir = "./Report"
    if not os.path.exists(report_dir):
        os.makedirs(report_dir)
        print(f"Created directory: {report_dir}")

    try:
        result = subprocess.run(["sbatch", script_path], capture_output=True, text=True, check=True)
        job_id = result.stdout.strip().split()[-1]  # Extract the job ID from sbatch output
        print(f"Job submitted successfully: {result.stdout.strip()}")

        # Provide a hint for monitoring the job log file in real-time
        print("\nHint: Use the following command to monitor your job log file in real-time:")
        print(f"watch tail -n 20 {report_dir}/{job_id}-slurm.out")

    except subprocess.CalledProcessError as e:
        print(f"Error submitting job: {e.stderr.strip()}")


def run_interactive(args):
    """
    Construct an srun command to run an interactive bash session, honoring the same resources
    (partition, cpus_per_task, gpus, memory, etc.) as in non-interactive mode.
    """
    # Auto-detect resources if not explicitly specified (similar to generate_sbatch_script)
    if args.partition is None or args.nodes is None or args.cpus_per_task is None or args.memory is None:
        best_partition, best_nodes, best_cpus_per_task, best_memory, best_gpus = get_node_resources()
        args.partition = args.partition or best_partition
        args.nodes = args.nodes or best_nodes
        args.cpus_per_task = args.cpus_per_task or best_cpus_per_task
        args.memory = args.memory or best_memory
        args.gpus = args.gpus or best_gpus

    # Auto-detect account if needed (though typically account is less often used for interactive srun)
    args.account = args.account or get_default_account()

    # Build the srun command
    srun_cmd = ["srun"]

    # Add partition if specified
    if args.partition:
        srun_cmd.append(f"--partition={args.partition}")
    # Add account if specified
    if args.account:
        srun_cmd.append(f"--account={args.account}")
    # Number of nodes
    if args.nodes:
        srun_cmd.append(f"-N {args.nodes}")
    # Tasks per node
    if args.tasks_per_node:
        srun_cmd.append(f"--ntasks-per-node={args.tasks_per_node}")
    # CPUs per task
    if args.cpus_per_task:
        srun_cmd.append(f"--cpus-per-task={args.cpus_per_task}")
    # Memory
    if args.memory:
        srun_cmd.append(f"--mem={args.memory}")
    # GPUs
    if args.gpus:
        srun_cmd.append(f"--gres=gpu:{args.gpus}")
    # Time
    if args.time:
        srun_cmd.append(f"--time={args.time}")
    # Nodelist
    if args.nodelist:
        srun_cmd.append(f"--nodelist={args.nodelist}")
    # Exclude
    if args.exclude:
        srun_cmd.append(f"--exclude={args.exclude}")

    srun_cmd.append(f"--pty")
    srun_cmd.append("bash")

    print(f"Starting interactive session with:\n  {' '.join(srun_cmd)}")
    subprocess.run(srun_cmd)


def main():
    """
    Main entry point for the wrun command.
    - If the user runs 'bash' or uses --interactive, we run srun directly with resource config.
    - Otherwise, we generate an sbatch script and submit it.
    """
    parser = argparse.ArgumentParser(description="Generate and execute SLURM jobs.")
    parser.add_argument("--nodes", type=int, help="Number of nodes")
    parser.add_argument("--partition", help="Partition name (e.g., compute, debug, etc.)")
    parser.add_argument("--account", help="SLURM account (optional, auto-detected if not specified)")
    parser.add_argument("--tasks-per-node", type=int, default=1, help="Number of tasks per node")
    parser.add_argument("--cpus-per-task", default=10, type=int, help="CPU cores per task")
    parser.add_argument("--memory", default="50G", help="Memory per node (e.g., 50G)")
    parser.add_argument("--gpus", type=int, help="Number of GPUs per node")
    parser.add_argument("--time", default="4-00:00:00", help="Maximum job time (e.g., 4-00:00:00)")
    parser.add_argument("--nodelist", help="Comma-separated list of specific nodes to use")
    parser.add_argument("--exclude", help="Comma-separated list of nodes to exclude")
    parser.add_argument("--interactive", action="store_true", help="Enable interactive mode (start bash shell)")
    parser.add_argument("command", nargs="?", default="", help="Command to execute (defaults to bash)")
    args = parser.parse_args()

    # If no command is provided, default to "bash"
    args.command = args.command or "bash"

    # If user wants interactive mode or the command is literally "bash"
    if args.command.strip() == "bash" or args.interactive:
        run_interactive(args)
    else:
        # Otherwise, generate sbatch script and submit
        script_path = generate_sbatch_script(args)
        submit_sbatch(script_path)
