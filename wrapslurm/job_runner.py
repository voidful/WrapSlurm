import argparse
import os
import subprocess
from datetime import datetime

DEFAULT_SLURM_TEMPLATE = """#!/bin/bash
#SBATCH -N {nodes}
#SBATCH -p {partition}
#SBATCH --account={account}
#SBATCH --ntasks-per-node={tasks_per_node}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --mem={memory}
#SBATCH --gres=gpu:{gpus}
#SBATCH --time={time}
#SBATCH -o ./slurm-report/%j-slurm.out
{nodelist_option}{exclude_option}

# SLURM Environment Variables
echo "SLURM_NNODES=${{SLURM_NNODES}}"
echo "NODELIST=${{SLURM_JOB_NODELIST}}"
echo "SLURM_NODEID=${{SLURM_NODEID}}"
echo "SLURM_ARRAY_TASK_ID=${{SLURM_ARRAY_TASK_ID}}"

# Distributed Training Setup
export MASTER_ADDR=$(scontrol show hostnames ${{SLURM_JOB_NODELIST}} | head -n 1)
export MASTER_PORT=$(shuf -i 1024-65535 -n 1)
export TORCH_NCCL_ASYNC_ERROR_HANDLING=1
export CUDA_LAUNCH_BLOCKING=1
export TORCH_DISTRIBUTED_DEBUG=DETAIL

# Command Execution
srun --wait=60 --kill-on-bad-exit=1 --mpi=pmix bash -c "{command}"
"""

def get_default_account():
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
        return result.strip().split("\n")[0].strip() or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("Unable to retrieve default SLURM account. Ensure 'sacctmgr' is installed.")

def get_node_resources():
    try:
        result = subprocess.check_output(["sinfo", "--format=%P|%N|%C|%m", "--noheader"], text=True).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("Unable to query SLURM resources. Ensure 'sinfo' is installed.")

    best_partition, best_cpus, best_memory, best_gpus = None, 1, "50G", 1
    for line in result.split("\n"):
        parts = line.split("|")
        if len(parts) < 4:
            continue
        partition, _, cpu_info, memory = parts[:4]
        partition = partition.split("*")[0].strip()
        cpus_total = int(cpu_info.split("/")[-1])
        memory_mb = int("".join(filter(str.isdigit, memory))) if memory else 0
        memory_gb = f"{memory_mb // 1024}G" if memory_mb > 0 else "50G"
        if not best_partition or cpus_total > best_cpus:
            best_partition, best_cpus, best_memory = partition, cpus_total, memory_gb
    return best_partition, 1, best_cpus, best_memory, best_gpus

def generate_sbatch_script(args):
    if not all([args.partition, args.nodes, args.cpus_per_task, args.memory]):
        best_partition, best_nodes, best_cpus, best_memory, best_gpus = get_node_resources()
        args.partition = args.partition or best_partition
        args.nodes = args.nodes or best_nodes
        args.cpus_per_task = args.cpus_per_task or best_cpus
        args.memory = args.memory or best_memory
        args.gpus = args.gpus or best_gpus

    args.account = args.account or get_default_account()
    nodelist_option = f"#SBATCH --nodelist={args.nodelist}\n" if args.nodelist else ""
    exclude_option = f"#SBATCH --exclude={args.exclude}\n" if args.exclude else ""

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

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_name = f"job_{timestamp}.sbatch"
    script_path = os.path.join(os.getcwd(), './slurm_run/', script_name)

    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(sbatch_script)
    print(f"Generated sbatch script: {script_path}")
    return script_path

def submit_sbatch(script_path):
    report_dir = "./slurm-report"
    os.makedirs(report_dir, exist_ok=True)
    try:
        result = subprocess.run(["sbatch", script_path], capture_output=True, text=True, check=True)
        job_id = result.stdout.strip().split()[-1]
        print(f"Job submitted: {result.stdout.strip()}")
        print(f"Monitor logs: watch tail -n 20 {os.path.join(report_dir, f'{job_id}-slurm.out')}")
    except subprocess.CalledProcessError as e:
        print(f"Error submitting job: {e.stderr.strip()}")

def run_interactive(args):
    if not all([args.partition, args.nodes, args.cpus_per_task, args.memory]):
        best_partition, best_nodes, best_cpus, best_memory, best_gpus = get_node_resources()
        args.partition = args.partition or best_partition
        args.nodes = args.nodes or best_nodes
        args.cpus_per_task = args.cpus_per_task or best_cpus
        args.memory = args.memory or best_memory
        args.gpus = args.gpus or best_gpus

    args.account = args.account or get_default_account()
    srun_cmd = [
        "srun",
        f"--partition={args.partition}",
        f"--account={args.account}",
        f"-N {args.nodes}",
        f"--ntasks-per-node={args.tasks_per_node}",
        f"--cpus-per-task={args.cpus_per_task}",
        f"--mem={args.memory}",
        f"--gres=gpu:{args.gpus}",
        f"--time={args.time}",
        "--pty",
        "bash"
    ]
    if args.nodelist:
        srun_cmd.insert(-2, f"--nodelist={args.nodelist}")
    if args.exclude:
        srun_cmd.insert(-2, f"--exclude={args.exclude}")
    print(f"Starting interactive session with: {' '.join(srun_cmd)}")
    subprocess.run(srun_cmd)

def main():
    parser = argparse.ArgumentParser(description="SLURM job manager.")
    parser.add_argument("--nodes", type=int, help="Number of nodes")
    parser.add_argument("--partition", help="Partition name")
    parser.add_argument("--account", help="SLURM account")
    parser.add_argument("--tasks-per-node", type=int, default=1, help="Tasks per node")
    parser.add_argument("--cpus-per-task", type=int, default=10, help="CPU cores per task")
    parser.add_argument("--memory", help="Memory per node (e.g., 50G)")
    parser.add_argument("--gpus", type=int, help="GPUs per node")
    parser.add_argument("--time", default="4-00:00:00", help="Job time limit")
    parser.add_argument("--nodelist", help="Nodes to include")
    parser.add_argument("--exclude", help="Nodes to exclude")
    parser.add_argument("--interactive", action="store_true", help="Start an interactive session")
    parser.add_argument("command", nargs="?", default="", help="Command to execute")
    args = parser.parse_args()

    if args.interactive or args.command.strip() == "bash":
        run_interactive(args)
    else:
        script_path = generate_sbatch_script(args)
        submit_sbatch(script_path)

if __name__ == "__main__":
    main()
