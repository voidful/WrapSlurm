"""Interactive terminal UI for selecting SLURM job parameters."""

from typing import Dict, List, Optional

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


def prompt_partition(partitions: Dict[str, "PartitionInfo"], default: Optional[str] = None) -> str:
    """Prompt user to select a partition from available options."""
    if not QUESTIONARY_AVAILABLE:
        return default or ""
    
    choices = []
    for name, info in sorted(partitions.items()):
        label = f"{name} (CPUs: {info.cpus_per_node}, Mem: {info.memory_display}, GPUs: {info.gpus})"
        choices.append(questionary.Choice(title=label, value=name))
    
    # Set default selection
    default_idx = 0
    if default:
        for idx, choice in enumerate(choices):
            if choice.value == default:
                default_idx = idx
                break
    
    result = questionary.select(
        "Select partition:",
        choices=choices,
        default=choices[default_idx] if choices else None,
        style=CUSTOM_STYLE,
    ).ask()
    
    return result or (default if default else "")


def prompt_account(default: Optional[str] = None) -> str:
    """Prompt user to input account name."""
    if not QUESTIONARY_AVAILABLE:
        return default or ""
    
    result = questionary.text(
        "Enter account:",
        default=default or "",
        style=CUSTOM_STYLE,
    ).ask()
    
    return result or (default if default else "")


def prompt_nodes(default: int = 1) -> int:
    """Prompt user to select number of nodes."""
    if not QUESTIONARY_AVAILABLE:
        return default
    
    choices = [str(i) for i in range(1, 17)]
    default_str = str(default)
    
    result = questionary.select(
        "Select number of nodes:",
        choices=choices,
        default=default_str,
        style=CUSTOM_STYLE,
    ).ask()
    
    return int(result) if result else default


def prompt_tasks_per_node(default: int = 1, max_val: int = 8) -> int:
    """Prompt user to select tasks per node."""
    if not QUESTIONARY_AVAILABLE:
        return default
    
    choices = [str(i) for i in range(1, max_val + 1)]
    default_str = str(min(default, max_val))
    
    result = questionary.select(
        "Select tasks per node:",
        choices=choices,
        default=default_str,
        style=CUSTOM_STYLE,
    ).ask()
    
    return int(result) if result else default


def prompt_cpus_per_task(default: int, max_val: int) -> int:
    """Prompt user to select CPUs per task."""
    if not QUESTIONARY_AVAILABLE:
        return default
    
    # Generate sensible CPU options
    options = [1, 2, 4, 8, 16, 32, 64, 128]
    choices = [str(c) for c in options if c <= max_val]
    if str(max_val) not in choices:
        choices.append(str(max_val))
    
    default_str = str(default) if str(default) in choices else choices[-1]
    
    result = questionary.select(
        "Select CPUs per task:",
        choices=choices,
        default=default_str,
        style=CUSTOM_STYLE,
    ).ask()
    
    return int(result) if result else default


def prompt_memory(default: str = "50G") -> str:
    """Prompt user to input memory allocation."""
    if not QUESTIONARY_AVAILABLE:
        return default
    
    # Common memory options
    choices = ["16G", "32G", "50G", "64G", "100G", "128G", "200G", "256G", "500G", "Custom..."]
    
    # Determine default index
    default_idx = None
    for idx, choice in enumerate(choices):
        if choice == default:
            default_idx = idx
            break
    
    result = questionary.select(
        "Select memory:",
        choices=choices,
        default=choices[default_idx] if default_idx is not None else default,
        style=CUSTOM_STYLE,
    ).ask()
    
    if result == "Custom...":
        result = questionary.text(
            "Enter memory (e.g., 50G, 200G):",
            default=default,
            style=CUSTOM_STYLE,
        ).ask()
    
    return result or default


def prompt_gpus(default: int = 1, max_val: int = 8) -> int:
    """Prompt user to select number of GPUs."""
    if not QUESTIONARY_AVAILABLE:
        return default
    
    choices = [str(i) for i in range(0, max_val + 1)]
    default_str = str(min(default, max_val))
    
    result = questionary.select(
        "Select number of GPUs:",
        choices=choices,
        default=default_str,
        style=CUSTOM_STYLE,
    ).ask()
    
    return int(result) if result else default


def prompt_time(default: str = "4-00:00:00") -> str:
    """Prompt user to input time limit."""
    if not QUESTIONARY_AVAILABLE:
        return default
    
    # Common time options
    choices = [
        "1:00:00",      # 1 hour
        "4:00:00",      # 4 hours
        "12:00:00",     # 12 hours
        "1-00:00:00",   # 1 day
        "2-00:00:00",   # 2 days
        "4-00:00:00",   # 4 days
        "7-00:00:00",   # 7 days
        "Custom...",
    ]
    
    # Try to find default in choices
    default_choice = default if default in choices else "Custom..."
    
    result = questionary.select(
        "Select time limit:",
        choices=choices,
        default=default_choice,
        style=CUSTOM_STYLE,
    ).ask()
    
    if result == "Custom...":
        result = questionary.text(
            "Enter time limit (e.g., 4-00:00:00):",
            default=default,
            style=CUSTOM_STYLE,
        ).ask()
    
    return result or default


def prompt_missing_params(
    missing_fields: List[str],
    partition_infos: Dict[str, "PartitionInfo"],
    defaults: Dict[str, object],
) -> Dict[str, object]:
    """
    Prompt user for all missing parameters.
    
    Args:
        missing_fields: List of field names that need values
        partition_infos: Available partitions from sinfo
        defaults: Current default values
    
    Returns:
        Dictionary of field names to selected values
    """
    if not QUESTIONARY_AVAILABLE:
        print("Warning: questionary not installed. Using defaults.")
        return {}
    
    results: Dict[str, object] = {}
    selected_partition_info = None
    
    # Prompt for partition first since other defaults depend on it
    if "partition" in missing_fields:
        partition = prompt_partition(partition_infos, defaults.get("partition"))
        results["partition"] = partition
        selected_partition_info = partition_infos.get(partition)
    elif defaults.get("partition"):
        selected_partition_info = partition_infos.get(str(defaults.get("partition")))
    
    # Get partition info for smart defaults
    if selected_partition_info is None and partition_infos:
        selected_partition_info = max(
            partition_infos.values(),
            key=lambda info: (info.cpus_per_node, info.gpus, info.memory_mb),
        )
    
    # Account
    if "account" in missing_fields:
        results["account"] = prompt_account(defaults.get("account"))
    
    # Nodes
    if "nodes" in missing_fields:
        results["nodes"] = prompt_nodes(defaults.get("nodes", 1))
    
    # Tasks per node
    if "tasks_per_node" in missing_fields:
        max_tasks = 8
        if selected_partition_info:
            max_tasks = min(selected_partition_info.gpus or 8, 8)
        results["tasks_per_node"] = prompt_tasks_per_node(
            defaults.get("tasks_per_node", 1),
            max_val=max_tasks,
        )
    
    # CPUs per task
    if "cpus_per_task" in missing_fields:
        max_cpus = 128
        default_cpus = 8
        if selected_partition_info:
            max_cpus = selected_partition_info.cpus_per_node
            default_cpus = max_cpus
        results["cpus_per_task"] = prompt_cpus_per_task(
            defaults.get("cpus_per_task", default_cpus),
            max_val=max_cpus,
        )
    
    # Memory
    if "memory" in missing_fields:
        default_mem = "50G"
        if selected_partition_info:
            default_mem = selected_partition_info.memory_display
        results["memory"] = prompt_memory(defaults.get("memory", default_mem))
    
    # GPUs
    if "gpus" in missing_fields:
        max_gpus = 8
        default_gpus = 1
        if selected_partition_info:
            max_gpus = selected_partition_info.gpus or 8
            default_gpus = max_gpus
        results["gpus"] = prompt_gpus(
            defaults.get("gpus", default_gpus),
            max_val=max_gpus,
        )
    
    # Time
    if "time" in missing_fields:
        default_time = "4-00:00:00"
        if selected_partition_info and selected_partition_info.max_time:
            default_time = selected_partition_info.max_time
        results["time"] = prompt_time(defaults.get("time", default_time))
    
    return results


def is_interactive_available() -> bool:
    """Check if interactive mode is available."""
    return QUESTIONARY_AVAILABLE
