import argparse
import subprocess
import re

try:
    from terminaltables import AsciiTable
except ImportError:  # pragma: no cover - fallback when dependency missing
    class AsciiTable:
        def __init__(self, data):
            self.table = "\n".join(" | ".join(map(str, row)) for row in data)
        justify_columns = {}

try:
    from termcolor import colored
except ImportError:  # pragma: no cover - fallback to no-op
    def colored(text, *_args, **_kwargs):
        return text


def get_node_info(include_down=False):
    """
    Extract detailed node information using 'scontrol show node'.
    """
    try:
        result = subprocess.check_output(["scontrol", "show", "node"], text=True).strip()
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error while executing scontrol: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("Command 'scontrol' not found. Please ensure SLURM is installed and added to PATH.")

    # Each node's details are separated by a blank line
    nodes_data = result.split("\n\n")
    nodes = []

    for node_data in nodes_data:
        node = parse_node_data(node_data)
        if node:
            if not include_down and ('drain' in node["State"].lower() or 'down' in node["State"].lower()):
                continue
            nodes.append(node)

    return nodes


def parse_node_data(data):
    """
    Parse information for a single node from 'scontrol show node' output.
    """
    # Extract node name
    node_name_match = re.search(r"NodeName=(\S+)", data)
    if not node_name_match:
        return None
    node_name = node_name_match.group(1)

    # Extract memory details
    real_memory_match = re.search(r"RealMemory=(\d+)", data)
    alloc_memory_match = re.search(r"AllocMem=(\d+)", data)
    real_memory = int(real_memory_match.group(1)) if real_memory_match else 0
    alloc_memory = int(alloc_memory_match.group(1)) if alloc_memory_match else 0
    memory_usage_percentage = (alloc_memory / real_memory) * 100 if real_memory > 0 else 0

    # Extract CPU details
    cpu_alloc_match = re.search(r"CPUAlloc=(\d+)", data)
    cpu_total_match = re.search(r"CPUTot=(\d+)", data)
    cpu_load_match = re.search(r"CPULoad=(\S+)", data)
    cpu_alloc = int(cpu_alloc_match.group(1)) if cpu_alloc_match else 0
    cpu_total = int(cpu_total_match.group(1)) if cpu_total_match else 0
    cpu_load = float(cpu_load_match.group(1)) if cpu_load_match else 0.0
    cpu_usage_percentage = (cpu_alloc / cpu_total) * 100 if cpu_total > 0 else 0

    # Extract GPU details
    gpu_total = 0
    gpu_alloc = 0

    cfg_tres_match = re.search(r"CfgTRES=([^\n]*)", data)
    if cfg_tres_match:
        cfg = cfg_tres_match.group(1)
        m = re.search(r"gres/gpu=(\d+)", cfg)
        if m:
            gpu_total = int(m.group(1))

    alloc_tres_match = re.search(r"AllocTRES=([^\n]*)", data)
    if alloc_tres_match:
        alloc = alloc_tres_match.group(1)
        m = re.search(r"gres/gpu=(\d+)", alloc)
        if m:
            gpu_alloc = int(m.group(1))

    if gpu_total == 0:
        gres_match = re.search(r"Gres=\S*?gpu[^:]*:(\d+)", data)
        if gres_match:
            gpu_total = int(gres_match.group(1))

    if gpu_alloc == 0:
        gres_used_match = re.search(r"GresUsed=\S*?gpu:(\d+)", data)
        if gres_used_match:
            gpu_alloc = int(gres_used_match.group(1))

    # Extract state
    state_match = re.search(r"State=(\S+)", data)
    state = state_match.group(1) if state_match else "UNKNOWN"

    # Extract partitions
    partitions_match = re.search(r"Partitions=(\S+)", data)
    partitions = partitions_match.group(1) if partitions_match else "UNKNOWN"

    return {
        "NodeName": node_name,
        "State": state,
        "Partitions": partitions,
        "CPUs": f"{cpu_alloc} Alloc ({cpu_usage_percentage:.1f}%) / {cpu_total} Total",
        "Memory": f"{alloc_memory // 1024} GB Used / {real_memory // 1024} GB ({memory_usage_percentage:.1f}%)",
        "CPUAlloc": cpu_alloc,
        "CPUTot": cpu_total,
        "CPULoad": cpu_load,
        "GPUAlloc": gpu_alloc,
        "GPUTot": gpu_total,
    }


def color_state(state):
    """
    Add color to node states for better readability.
    """
    state_lower = state.lower()
    if "idle" in state_lower:
        return colored(state, "green", attrs=["bold"])
    elif "mix" in state_lower:
        return colored(state, "yellow", attrs=["bold"])
    elif "drain" in state_lower or "down" in state_lower:
        return colored(state, "red", attrs=["bold"])
    else:
        return colored(state, "cyan", attrs=["bold"])


def display_nodes(nodes, graph=False):
    """
    Display node information in a table format. If ``graph`` is True, show a
    simple GPU usage graph with one column per GPU.
    """
    if not nodes:
        print("No node information to display.")
        return

    if graph:
        return display_nodes_graph(nodes)

    titles = ["NodeName", "State", "Partitions", "CPUs", "Memory"]

    rows = []
    for node in nodes:
        rows.append([
            node["NodeName"],
            color_state(node["State"]),
            node["Partitions"],
            node["CPUs"],
            node["Memory"]
        ])

    table = AsciiTable([titles] + rows)
    for i in range(len(titles)):
        table.justify_columns[i] = "left"
    table.justify_columns[0] = "right"

    output = table.table
    print(output)
    return output


def display_nodes_graph(nodes, slots=8):
    """Display nodes with an ASCII GPU usage graph."""
    max_slots = max([n.get("GPUTot", 0) for n in nodes] + [slots])
    titles = ["NodeName"] + [f" #{i+1} " for i in range(max_slots)] + ["CPUld", "State"]

    rows = []
    for node in nodes:
        total = node.get("GPUTot", max_slots)
        used = min(node.get("GPUAlloc", 0), total)
        bar = []
        for i in range(max_slots):
            if i < used:
                bar.append("#")
            elif i < total:
                bar.append(" ")
            else:
                bar.append("")
        rows.append([
            node["NodeName"],
            *bar,
            f"{node.get('CPULoad', 0):.2f}",
            color_state(node["State"]),
        ])

    table = AsciiTable([titles] + rows)
    for i in range(len(titles)):
        table.justify_columns[i] = "left"
    table.justify_columns[0] = "right"

    output = table.table
    print(output)
    return output


def main():
    """
    Entry point for the 'winfo' command.
    """
    parser = argparse.ArgumentParser(
        description="Display SLURM node information with options to include 'down' or 'drain' nodes."
    )
    parser.add_argument(
        "--include-down",
        action="store_true",
        help="Include nodes in 'down' or 'drain' states."
    )
    parser.add_argument(
        "--graph",
        action="store_true",
        help="Display nodes with an ASCII GPU usage graph."
    )
    args = parser.parse_args()

    try:
        nodes = get_node_info(include_down=args.include_down)
        display_nodes(nodes, graph=args.graph)
    except RuntimeError as e:
        print(f"Error: {e}")
