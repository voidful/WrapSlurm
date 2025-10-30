"""User friendly front-end for submitting SLURM jobs."""

import argparse
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency used for rich tables
    from terminaltables import AsciiTable
except ImportError:  # pragma: no cover
    AsciiTable = None

try:  # pragma: no cover - colour output is optional in tests
    from termcolor import colored
except ImportError:  # pragma: no cover
    def colored(text, *_args, **_kwargs):
        return text

DEFAULT_SLURM_TEMPLATE = """#!/bin/bash
#SBATCH -N {nodes}
#SBATCH -p {partition}
#SBATCH --account={account}
#SBATCH --ntasks-per-node={tasks_per_node}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --mem={memory}
#SBATCH --gres=gpu:{gpus}
#SBATCH --time={time}
#SBATCH -o {report_dir}/%j-slurm.out
{job_name_line}{nodelist_option}{exclude_option}

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
srun --wait=60 --kill-on-bad-exit=1 --mpi=pmix bash -lc {command}
"""


@dataclass
class JobConfig:
    """Normalized configuration for a SLURM job submission."""

    nodes: int
    partition: str
    account: str
    tasks_per_node: int
    cpus_per_task: int
    memory: str
    gpus: int
    time: str
    report_dir: str
    command: Sequence[str] = field(default_factory=list)
    nodelist: Optional[str] = None
    exclude: Optional[str] = None
    job_name: Optional[str] = None
    interactive: bool = False

    def command_for_display(self) -> str:
        if self.interactive:
            return "Interactive shell"
        if not self.command:
            return "<no command provided>"
        return " ".join(self.command)

    def command_for_script(self) -> str:
        if not self.command:
            raise ValueError("Batch jobs require a command to execute.")
        command_line = shlex.join(self.command)
        # Quote the entire command so that it is passed as a single argument to bash -lc.
        return shlex.quote(command_line)

def get_default_account() -> str:
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

def get_node_resources() -> Tuple[str, int, int, str, int]:
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

def build_sbatch_script(config: JobConfig) -> str:
    nodelist_option = f"#SBATCH --nodelist={config.nodelist}\n" if config.nodelist else ""
    exclude_option = f"#SBATCH --exclude={config.exclude}\n" if config.exclude else ""
    job_name_line = f"#SBATCH -J {config.job_name}\n" if config.job_name else ""
    return DEFAULT_SLURM_TEMPLATE.format(
        nodes=config.nodes,
        partition=config.partition,
        account=config.account,
        tasks_per_node=config.tasks_per_node,
        cpus_per_task=config.cpus_per_task,
        memory=config.memory,
        gpus=config.gpus,
        time=config.time,
        report_dir=config.report_dir,
        nodelist_option=nodelist_option,
        exclude_option=exclude_option,
        job_name_line=job_name_line,
        command=config.command_for_script(),
    )


def generate_sbatch_script(config: JobConfig, script_dir: str) -> str:
    sbatch_script = build_sbatch_script(config)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_name = f"job_{timestamp}.sbatch"
    script_path = os.path.join(os.getcwd(), script_dir, script_name)

    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(sbatch_script)
    print(f"Generated sbatch script: {script_path}")
    return script_path


def submit_sbatch(script_path: str, report_dir: str) -> None:
    os.makedirs(report_dir, exist_ok=True)
    try:
        result = subprocess.run(["sbatch", script_path], capture_output=True, text=True, check=True)
        job_id = result.stdout.strip().split()[-1]
        print(f"Job submitted: {result.stdout.strip()}")
        print(
            "Monitor logs: watch tail -n 20 "
            f"{os.path.join(report_dir, f'{job_id}-slurm.out')}"
        )
    except subprocess.CalledProcessError as e:
        print(f"Error submitting job: {e.stderr.strip()}")

def run_interactive(config: JobConfig) -> None:
    srun_cmd = [
        "srun",
        f"--partition={config.partition}",
        f"--account={config.account}",
        f"-N {config.nodes}",
        f"--ntasks-per-node={config.tasks_per_node}",
        f"--cpus-per-task={config.cpus_per_task}",
        f"--mem={config.memory}",
        f"--gres=gpu:{config.gpus}",
        f"--time={config.time}",
        "--pty",
        "bash"
    ]
    if config.nodelist:
        srun_cmd.insert(-2, f"--nodelist={config.nodelist}")
    if config.exclude:
        srun_cmd.insert(-2, f"--exclude={config.exclude}")
    print(f"Starting interactive session with: {' '.join(srun_cmd)}")
    subprocess.run(srun_cmd)

def highlight_value(value: str, field: str, auto_fields: Iterable[str]) -> str:
    if field in auto_fields:
        return colored(f"{value} *", "cyan")
    return str(value)


def print_job_summary(
    config: JobConfig,
    auto_fields: Iterable[str],
    mode: str,
    script_path: Optional[str] = None,
) -> None:
    rows = [
        ("Mode", mode),
        ("Partition", highlight_value(config.partition, "partition", auto_fields)),
        ("Account", highlight_value(config.account, "account", auto_fields)),
        ("Nodes", highlight_value(config.nodes, "nodes", auto_fields)),
        (
            "Tasks / Node",
            highlight_value(config.tasks_per_node, "tasks_per_node", auto_fields),
        ),
        (
            "CPUs / Task",
            highlight_value(config.cpus_per_task, "cpus_per_task", auto_fields),
        ),
        ("Memory", highlight_value(config.memory, "memory", auto_fields)),
        ("GPUs", highlight_value(config.gpus, "gpus", auto_fields)),
        ("Time", config.time),
        ("Command", config.command_for_display()),
    ]

    if config.nodelist:
        rows.append(("NodeList", config.nodelist))
    if config.exclude:
        rows.append(("Exclude", config.exclude))
    if config.job_name:
        rows.append(("Job Name", config.job_name))
    rows.append(("Log Dir", config.report_dir))
    if script_path:
        rows.append(("Script", script_path))

    if AsciiTable:
        table = AsciiTable([["Setting", "Value"]] + list(rows))
        table.justify_columns[0] = "right"
        for col in range(1, len(table.table_data[0])):
            table.justify_columns[col] = "left"
        print(table.table)
    else:  # pragma: no cover - fallback formatting for missing dependency
        for setting, value in rows:
            print(f"{setting:>12}: {value}")

    if auto_fields:
        print(colored("* Automatically detected value", "cyan"))


def resolve_job_config(args: argparse.Namespace) -> Tuple[JobConfig, List[str]]:
    auto_fields: List[str] = []
    nodes = args.nodes
    partition = args.partition
    cpus_per_task = args.cpus_per_task
    memory = args.memory
    gpus = args.gpus

    detection_needed = any(value is None for value in (partition, nodes, cpus_per_task, memory, gpus))
    best_partition = best_nodes = best_cpus = best_memory = best_gpus = None
    if detection_needed:
        best_partition, best_nodes, best_cpus, best_memory, best_gpus = get_node_resources()

    if partition is None and best_partition is not None:
        partition = best_partition
        auto_fields.append("partition")
    if nodes is None and best_nodes is not None:
        nodes = best_nodes
        auto_fields.append("nodes")
    if cpus_per_task is None and best_cpus is not None:
        cpus_per_task = best_cpus
        auto_fields.append("cpus_per_task")
    if memory is None and best_memory is not None:
        memory = best_memory
        auto_fields.append("memory")
    if gpus is None and best_gpus is not None:
        gpus = best_gpus
        auto_fields.append("gpus")

    if partition is None or nodes is None or cpus_per_task is None or memory is None or gpus is None:
        raise RuntimeError(
            "Unable to determine required resources. Provide the missing flags or ensure 'sinfo' is available."
        )

    try:
        account = args.account or get_default_account()
        if args.account is None:
            auto_fields.append("account")
    except RuntimeError as exc:
        raise RuntimeError(str(exc))

    command_parts: Sequence[str] = list(args.command or [])
    interactive = args.interactive
    if not command_parts:
        interactive = True
    elif len(command_parts) == 1 and command_parts[0].strip() == "bash":
        interactive = True

    config = JobConfig(
        nodes=nodes,
        partition=partition,
        account=account,
        tasks_per_node=args.tasks_per_node,
        cpus_per_task=cpus_per_task,
        memory=memory,
        gpus=gpus,
        time=args.time,
        report_dir=args.report_dir,
        command=command_parts,
        nodelist=args.nodelist,
        exclude=args.exclude,
        job_name=args.job_name,
        interactive=interactive,
    )

    return config, auto_fields


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit and manage SLURM jobs with sensible defaults and friendly output.",
    )
    parser.add_argument("--nodes", type=int, help="Number of nodes to request")
    parser.add_argument("--partition", help="Partition name to submit to")
    parser.add_argument("--account", help="SLURM account to charge")
    parser.add_argument("--tasks-per-node", type=int, default=1, help="Tasks per node (default: 1)")
    parser.add_argument("--cpus-per-task", type=int, help="CPU cores per task")
    parser.add_argument("--memory", help="Memory per node (e.g., 50G)")
    parser.add_argument("--gpus", type=int, help="GPUs per node")
    parser.add_argument("--time", default="4-00:00:00", help="Job time limit (default: 4-00:00:00)")
    parser.add_argument("--nodelist", help="Comma separated list of nodes to include")
    parser.add_argument("--exclude", help="Comma separated list of nodes to exclude")
    parser.add_argument("--job-name", help="Optional job name shown in SLURM accounting")
    parser.add_argument("--report-dir", default="./slurm-report", help="Directory where SLURM outputs logs")
    parser.add_argument("--script-dir", default="./slurm_run", help="Directory to store generated sbatch scripts")
    parser.add_argument("--interactive", action="store_true", help="Force an interactive srun session")
    parser.add_argument("--dry-run", action="store_true", help="Show the sbatch script without submitting")
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to execute for batch jobs (e.g. python train.py --epochs 10)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        config, auto_fields = resolve_job_config(args)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return

    mode = "Interactive" if config.interactive else "Batch"

    if config.interactive:
        print_job_summary(config, auto_fields, mode)
        run_interactive(config)
        return

    if args.dry_run:
        try:
            script_content = build_sbatch_script(config)
        except ValueError as exc:
            print(f"Error: {exc}")
            return
        print_job_summary(config, auto_fields, mode)
        print("\nDry run enabled – sbatch script preview:\n")
        print(script_content)
        return

    try:
        script_path = generate_sbatch_script(config, args.script_dir)
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    print_job_summary(config, auto_fields, mode, script_path=script_path)
    submit_sbatch(script_path, config.report_dir)

if __name__ == "__main__":
    main()
