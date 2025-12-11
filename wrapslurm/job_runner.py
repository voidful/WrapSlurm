"""User friendly front-end for submitting SLURM jobs."""

import argparse
import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency used for rich tables
    from terminaltables import AsciiTable
except ImportError:  # pragma: no cover
    AsciiTable = None

try:  # pragma: no cover - colour output is optional in tests
    from termcolor import colored
except ImportError:  # pragma: no cover
    def colored(text, *_args, **_kwargs):
        return text

from wrapslurm.interactive_config import (
    is_interactive_available,
    prompt_missing_params,
)

DEFAULT_SLURM_TEMPLATE = """#!/bin/bash
#SBATCH -N {nodes}
#SBATCH -p {partition}
#SBATCH --account={account}
#SBATCH --ntasks-per-node={tasks_per_node}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --mem={memory}
#SBATCH --gres=gpu:{gpus}
#SBATCH --time={time}
#SBATCH -o {report_dir}/%j.out
#SBATCH -e {report_dir}/%j.err
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


DEFAULT_REPORT_DIR = "./slurm-report"
DEFAULT_SCRIPT_DIR = "./slurm_run"
DEFAULT_TIME = "4-00:00:00"
DEFAULT_CONFIG_PATH = os.path.join(
    os.path.expanduser("~"), ".config", "wrapslurm", "defaults.json"
)

DEFAULT_FIELD_TYPES: Dict[str, type] = {
    "nodes": int,
    "tasks_per_node": int,
    "cpus_per_task": int,
    "gpus": int,
}


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


@dataclass
class PartitionInfo:
    """Summary of a partition's resource limits."""

    name: str
    cpus_per_node: int
    memory_mb: int
    memory_display: str
    gpus: int
    max_time: Optional[str]

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


def format_memory(memory_mb: int) -> str:
    if memory_mb <= 0:
        return "50G"
    if memory_mb % 1024 == 0:
        return f"{memory_mb // 1024}G"
    if memory_mb > 1024:
        return f"{memory_mb / 1024:.1f}G"
    return f"{memory_mb}M"


def parse_gpus(gres_field: str) -> int:
    if not gres_field:
        return 1
    for entry in gres_field.split(","):
        if "gpu" not in entry:
            continue
        numbers = re.findall(r"(\d+)", entry)
        if not numbers:
            continue
        try:
            count = int(numbers[-1])
            return max(1, count)
        except ValueError:
            continue
    return 1


def get_default(defaults: Dict[str, object], key: str) -> Optional[object]:
    if key not in defaults:
        return None
    value = defaults[key]
    target_type = DEFAULT_FIELD_TYPES.get(key)
    if target_type is not None and value is not None:
        try:
            return target_type(value)
        except (TypeError, ValueError):
            print(f"Ignoring stored default for {key!r}: {value!r}")
            return None
    return value


def load_user_defaults(path: str = DEFAULT_CONFIG_PATH) -> Dict[str, object]:
    try:
        with open(path, "r", encoding="utf-8") as config_file:
            data = json.load(config_file)
            if isinstance(data, dict):
                return data
            print(f"Ignoring malformed defaults at {path}: expected an object")
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        print(f"Ignoring corrupted defaults file at {path}")
    return {}


def save_user_defaults(updates: Dict[str, object], path: str = DEFAULT_CONFIG_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    defaults = load_user_defaults(path)
    defaults.update(updates)
    with open(path, "w", encoding="utf-8") as config_file:
        json.dump(defaults, config_file, indent=2)
    print(f"Saved defaults to {path}")


def collect_default_updates(args: argparse.Namespace) -> Dict[str, object]:
    fields = {
        "partition",
        "account",
        "nodes",
        "tasks_per_node",
        "cpus_per_task",
        "memory",
        "gpus",
        "time",
        "report_dir",
        "script_dir",
    }
    updates: Dict[str, object] = {}
    for field in fields:
        value = getattr(args, field, None)
        if value is not None:
            updates[field] = value
    return updates


def query_partition_resources() -> Dict[str, PartitionInfo]:
    try:
        result = subprocess.check_output(
            ["sinfo", "--format=%P|%c|%m|%G|%l", "--noheader"], text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError("Unable to query SLURM resources. Ensure 'sinfo' is installed.")

    partitions: Dict[str, PartitionInfo] = {}
    for line in result.split("\n"):
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 5:
            continue
        partition_name_raw, cpu_info, memory_raw, gres, max_time = parts[:5]
        partition_name = partition_name_raw.split("*")[0].strip()
        if not partition_name:
            continue
        cpu_pieces = [piece for piece in cpu_info.split("/") if piece]
        try:
            cpus_total = int(cpu_pieces[-1]) if cpu_pieces else 1
        except ValueError:
            cpus_total = 1
        memory_digits = "".join(filter(str.isdigit, memory_raw))
        try:
            memory_mb = int(memory_digits) if memory_digits else 0
        except ValueError:
            memory_mb = 0
        memory_display = format_memory(memory_mb)
        gpus = parse_gpus(gres)
        partition_info = partitions.get(partition_name)
        if partition_info is None or cpus_total > partition_info.cpus_per_node:
            partitions[partition_name] = PartitionInfo(
                name=partition_name,
                cpus_per_node=cpus_total,
                memory_mb=memory_mb,
                memory_display=memory_display,
                gpus=gpus,
                max_time=max_time.strip() or None,
            )
    return partitions

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
        stdout_log = os.path.join(report_dir, f"{job_id}.out")
        stderr_log = os.path.join(report_dir, f"{job_id}.err")
        print(f"Stdout log: {stdout_log}")
        print(f"Stderr log: {stderr_log}")
        print(f"Monitor logs: tail -n 20 -f {stdout_log}")
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

def highlight_value(
    value: str,
    field: str,
    auto_fields: Iterable[str],
    default_fields: Iterable[str],
) -> str:
    if field in auto_fields:
        return colored(f"{value} *", "cyan")
    if field in default_fields:
        return colored(f"{value} \u2020", "yellow")
    return str(value)


def print_job_summary(
    config: JobConfig,
    auto_fields: Iterable[str],
    default_fields: Iterable[str],
    mode: str,
    script_path: Optional[str] = None,
) -> None:
    rows = [
        ("Mode", mode),
        (
            "Partition",
            highlight_value(config.partition, "partition", auto_fields, default_fields),
        ),
        ("Account", highlight_value(config.account, "account", auto_fields, default_fields)),
        ("Nodes", highlight_value(config.nodes, "nodes", auto_fields, default_fields)),
        (
            "Tasks / Node",
            highlight_value(
                config.tasks_per_node,
                "tasks_per_node",
                auto_fields,
                default_fields,
            ),
        ),
        (
            "CPUs / Task",
            highlight_value(
                config.cpus_per_task,
                "cpus_per_task",
                auto_fields,
                default_fields,
            ),
        ),
        ("Memory", highlight_value(config.memory, "memory", auto_fields, default_fields)),
        ("GPUs", highlight_value(config.gpus, "gpus", auto_fields, default_fields)),
        ("Time", highlight_value(config.time, "time", auto_fields, default_fields)),
        ("Command", config.command_for_display()),
    ]

    if config.nodelist:
        rows.append(("NodeList", config.nodelist))
    if config.exclude:
        rows.append(("Exclude", config.exclude))
    if config.job_name:
        rows.append(("Job Name", config.job_name))
    rows.append(
        ("Log Dir", highlight_value(config.report_dir, "report_dir", auto_fields, default_fields))
    )
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
    if default_fields:
        print(colored("† Loaded from saved defaults", "yellow"))


def resolve_job_config(
    args: argparse.Namespace, defaults: Dict[str, object], use_defaults: bool = False
) -> Tuple[JobConfig, List[str], List[str], str]:
    auto_fields: List[str] = []
    default_fields: List[str] = []

    def use_default(current_value: Optional[object], key: str) -> Optional[object]:
        if current_value is not None:
            return current_value
        default_value = get_default(defaults, key)
        if default_value is not None:
            default_fields.append(key)
        return default_value

    partition = use_default(args.partition, "partition")
    nodes = use_default(args.nodes, "nodes")
    tasks_per_node = use_default(args.tasks_per_node, "tasks_per_node")
    cpus_per_task = use_default(args.cpus_per_task, "cpus_per_task")
    memory = use_default(args.memory, "memory")
    gpus = use_default(args.gpus, "gpus")
    time = use_default(args.time, "time")
    report_dir = use_default(args.report_dir, "report_dir") or DEFAULT_REPORT_DIR
    script_dir = use_default(args.script_dir, "script_dir") or DEFAULT_SCRIPT_DIR

    partition_infos: Dict[str, PartitionInfo] = {}
    partition_info: Optional[PartitionInfo] = None

    need_partition_data = (
        partition is None
        or cpus_per_task is None
        or memory is None
        or gpus is None
        or time is None
    )

    if need_partition_data:
        try:
            partition_infos = query_partition_resources()
        except RuntimeError as exc:
            if partition is None or cpus_per_task is None or memory is None or gpus is None:
                raise RuntimeError(str(exc))

    # Determine which fields are missing and need interactive prompts
    missing_fields: List[str] = []
    if partition is None:
        missing_fields.append("partition")
    if nodes is None:
        missing_fields.append("nodes")
    if tasks_per_node is None:
        missing_fields.append("tasks_per_node")
    if cpus_per_task is None:
        missing_fields.append("cpus_per_task")
    if memory is None:
        missing_fields.append("memory")
    if gpus is None:
        missing_fields.append("gpus")
    if time is None:
        missing_fields.append("time")
    if args.account is None and get_default(defaults, "account") is None:
        missing_fields.append("account")

    # Use interactive prompts if not using defaults mode and there are missing fields
    interactive_results: Dict[str, object] = {}
    if missing_fields and not use_defaults and is_interactive_available():
        interactive_results = prompt_missing_params(
            missing_fields=missing_fields,
            partition_infos=partition_infos,
            defaults=defaults,
        )
        # Apply interactive results
        if "partition" in interactive_results:
            partition = interactive_results["partition"]
        if "nodes" in interactive_results:
            nodes = interactive_results["nodes"]
        if "tasks_per_node" in interactive_results:
            tasks_per_node = interactive_results["tasks_per_node"]
        if "cpus_per_task" in interactive_results:
            cpus_per_task = interactive_results["cpus_per_task"]
        if "memory" in interactive_results:
            memory = interactive_results["memory"]
        if "gpus" in interactive_results:
            gpus = interactive_results["gpus"]
        if "time" in interactive_results:
            time = interactive_results["time"]

    if partition is None:
        if not partition_infos:
            raise RuntimeError(
                "Unable to determine partition. Provide --partition or ensure 'sinfo' is available."
            )
        partition_info = max(
            partition_infos.values(),
            key=lambda info: (info.cpus_per_node, info.gpus, info.memory_mb),
        )
        partition = partition_info.name
        auto_fields.append("partition")
    else:
        partition_info = partition_infos.get(str(partition)) if partition_infos else None

    if nodes is None:
        nodes = 1
        auto_fields.append("nodes")

    if tasks_per_node is None:
        tasks_per_node = 1
        auto_fields.append("tasks_per_node")

    if cpus_per_task is None:
        if partition_info is None:
            raise RuntimeError(
                "Unable to determine CPUs per task. Provide --cpus-per-task or ensure 'sinfo' is available."
            )
        cpus_per_task = partition_info.cpus_per_node
        auto_fields.append("cpus_per_task")

    if memory is None:
        if partition_info is None:
            raise RuntimeError(
                "Unable to determine memory. Provide --memory or ensure 'sinfo' is available."
            )
        memory = partition_info.memory_display
        auto_fields.append("memory")

    if gpus is None:
        if partition_info is not None:
            gpus = partition_info.gpus
        else:
            gpus = 1
        auto_fields.append("gpus")

    if time is None:
        if partition_info is not None and partition_info.max_time:
            time = partition_info.max_time
        else:
            time = DEFAULT_TIME
        auto_fields.append("time")

    try:
        account = use_default(args.account, "account")
        if account is None and "account" in interactive_results:
            account = interactive_results["account"]
        if account is None:
            account = get_default_account()
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
        nodes=int(nodes),
        partition=str(partition),
        account=str(account),
        tasks_per_node=int(tasks_per_node),
        cpus_per_task=int(cpus_per_task),
        memory=str(memory),
        gpus=int(gpus),
        time=str(time),
        report_dir=str(report_dir),
        command=command_parts,
        nodelist=args.nodelist,
        exclude=args.exclude,
        job_name=args.job_name,
        interactive=interactive,
    )

    return config, auto_fields, default_fields, script_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Submit and manage SLURM jobs with sensible defaults and friendly output.",
    )
    parser.add_argument("-N", "--nodes", type=int, help="Number of nodes to request")
    parser.add_argument("-p", "--partition", help="Partition name to submit to")
    parser.add_argument("-A", "--account", help="SLURM account to charge")
    parser.add_argument(
        "-n",
        "--tasks-per-node",
        type=int,
        help="Tasks per node (default: 1)",
    )
    parser.add_argument("-c", "--cpus-per-task", type=int, help="CPU cores per task")
    parser.add_argument("--mem", "--memory", dest="memory", help="Memory per node (e.g., 50G)")
    parser.add_argument("-G", "--gpus", type=int, help="GPUs per node")
    parser.add_argument(
        "-t",
        "--time",
        help="Job time limit (default: partition maximum when available)",
    )
    parser.add_argument("-w", "--nodelist", help="Comma separated list of nodes to include")
    parser.add_argument("-x", "--exclude", help="Comma separated list of nodes to exclude")
    parser.add_argument("-J", "--job-name", help="Optional job name shown in SLURM accounting")
    parser.add_argument(
        "--report-dir",
        help=f"Directory where SLURM outputs logs (default: {DEFAULT_REPORT_DIR})",
    )
    parser.add_argument(
        "--script-dir",
        help=f"Directory to store generated sbatch scripts (default: {DEFAULT_SCRIPT_DIR})",
    )
    parser.add_argument("-i", "--interactive", action="store_true", help="Force an interactive srun session")
    parser.add_argument("--dry-run", action="store_true", help="Show the sbatch script without submitting")
    parser.add_argument(
        "-d", "--defaults",
        action="store_true",
        help="Use auto-detected defaults without interactive prompts",
    )
    parser.add_argument(
        "--save-defaults",
        action="store_true",
        help="Persist the provided options as defaults and exit",
    )
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Command to execute for batch jobs (e.g. python train.py --epochs 10)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    defaults = load_user_defaults()

    if args.save_defaults:
        updates = collect_default_updates(args)
        if updates:
            save_user_defaults(updates)
        else:
            print("No values provided to save as defaults.")
        return

    try:
        config, auto_fields, default_fields, script_dir = resolve_job_config(
            args, defaults, use_defaults=args.defaults
        )
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return

    mode = "Interactive" if config.interactive else "Batch"

    if config.interactive:
        print_job_summary(config, auto_fields, default_fields, mode)
        run_interactive(config)
        return

    if args.dry_run:
        try:
            script_content = build_sbatch_script(config)
        except ValueError as exc:
            print(f"Error: {exc}")
            return
        print_job_summary(config, auto_fields, default_fields, mode)
        print("\nDry run enabled – sbatch script preview:\n")
        print(script_content)
        return

    try:
        script_path = generate_sbatch_script(config, script_dir)
    except ValueError as exc:
        print(f"Error: {exc}")
        return

    print_job_summary(config, auto_fields, default_fields, mode, script_path=script_path)
    submit_sbatch(script_path, config.report_dir)

if __name__ == "__main__":
    main()
