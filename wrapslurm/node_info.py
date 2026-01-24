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
    gpu_total_by_type = {}  # {gpu_type: total_count}
    gpu_alloc_by_type = {}  # {gpu_type: alloc_count}

    # Parse total GPU configuration from CfgTRES
    cfg_tres_match = re.search(r"CfgTRES=([^\n]*)", data)
    if cfg_tres_match:
        cfg = cfg_tres_match.group(1)
        m = re.search(r"gres/gpu=(\d+)", cfg)
        if m:
            gpu_total = int(m.group(1))
        
        # Extract GPU types and their total counts (e.g., gres/gpu:3090=2)
        gpu_type_matches = re.findall(r"gres/gpu:([a-zA-Z0-9]+)=(\d+)", cfg)
        for gpu_type, count in gpu_type_matches:
            gpu_total_by_type[gpu_type] = int(count)

    # Parse allocated GPUs from AllocTRES
    alloc_tres_match = re.search(r"AllocTRES=([^\n]*)", data)
    if alloc_tres_match:
        alloc = alloc_tres_match.group(1)
        # Extract total GPU allocation
        m = re.search(r"gres/gpu=(\d+)", alloc)
        if m:
            gpu_alloc = int(m.group(1))
        
        # Extract specific GPU types and their allocated counts (e.g., gres/gpu:3090=2)
        gpu_type_matches = re.findall(r"gres/gpu:([a-zA-Z0-9]+)=(\d+)", alloc)
        for gpu_type, count in gpu_type_matches:
            gpu_alloc_by_type[gpu_type] = int(count)

    # Also try Gres field for total GPUs if CfgTRES didn't have them
    if gpu_total == 0:
        gres_match = re.search(r"Gres=(\S+)", data)
        if gres_match:
            gres = gres_match.group(1)
            # Parse gpu:TYPE:COUNT format (e.g., gpu:3090:4)
            gres_type_matches = re.findall(r"gpu:([a-zA-Z0-9]+):(\d+)", gres)
            for gpu_type, count in gres_type_matches:
                gpu_total_by_type[gpu_type] = int(count)
                gpu_total += int(count)
            
            # Fallback: gpu:COUNT format
            if gpu_total == 0:
                m = re.search(r"gpu[^:]*:(\d+)", gres)
                if m:
                    gpu_total = int(m.group(1))

    if gpu_alloc == 0:
        gres_used_match = re.search(r"GresUsed=\S*?gpu:(\d+)", data)
        if gres_used_match:
            gpu_alloc = int(gres_used_match.group(1))

    # Calculate AVAILABLE GPUs by type (total - allocated)
    gpu_available_details = []
    for gpu_type, total_count in gpu_total_by_type.items():
        alloc_count = gpu_alloc_by_type.get(gpu_type, 0)
        available_count = total_count - alloc_count
        if available_count > 0:
            gpu_available_details.append(f"{gpu_type}={available_count}")

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
        "GPUDetails": ", ".join(gpu_available_details) if gpu_available_details else "",
        "GPUAllocByType": gpu_alloc_by_type,  # {gpu_type: alloc_count}
    }



def get_job_gpu_mapping():
    """
    Get mapping of jobs to nodes and their GPU allocations.
    Returns a dict: {node_name: [(job_id, gpu_type, gpu_count), ...]}
    """
    try:
        # Query squeue for job ID, node list, and GRES (GPU) allocation
        # Format: JobID|NodeList|TRES_PER_NODE or GRES
        result = subprocess.check_output(
            ["squeue", "-h", "-t", "R", "-o", "%i|%N|%b"],
            text=True,
            stderr=subprocess.PIPE
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    
    if not result:
        return {}
    
    job_mapping = {}
    
    for line in result.split('\n'):
        if not line.strip():
            continue
        
        parts = line.split('|')
        if len(parts) < 3:
            continue
        
        job_id = parts[0].strip()
        node_list = parts[1].strip()
        gres = parts[2].strip()
        
        # Parse GPU type and count from GRES
        # Formats: "gpu:3090:2", "gpu:2", "gres/gpu:3090=2", "gres/gpu=2"
        gpu_count = 0
        gpu_type = "gpu"  # Default type if not specified
        
        # Try to match "gpu:TYPE:COUNT" format (e.g., "gpu:3090:2")
        gpu_type_match = re.search(r'gpu:([a-zA-Z0-9]+):(\d+)', gres)
        if gpu_type_match:
            gpu_type = gpu_type_match.group(1)
            gpu_count = int(gpu_type_match.group(2))
        else:
            # Try to match "gpu:COUNT" format (e.g., "gpu:2")
            gpu_match = re.search(r'gpu[:\=](\d+)', gres)
            if gpu_match:
                gpu_count = int(gpu_match.group(1))
        
        # If no GPU allocation found, skip this job
        if gpu_count == 0:
            continue
        
        # Parse node list - handle single node or node ranges
        # Examples: "node01", "node[01-03]", "node01,node02"
        nodes = []
        if '[' in node_list:
            # Handle node range format like "hgpn[01-03,05]"
            base_match = re.match(r'([a-zA-Z]+)\[([^\]]+)\]', node_list)
            if base_match:
                base_name = base_match.group(1)
                range_part = base_match.group(2)
                
                for part in range_part.split(','):
                    if '-' in part:
                        # Range like "01-03"
                        start, end = part.split('-')
                        # Preserve leading zeros
                        width = len(start)
                        for i in range(int(start), int(end) + 1):
                            nodes.append(f"{base_name}{str(i).zfill(width)}")
                    else:
                        # Single number
                        nodes.append(f"{base_name}{part}")
        else:
            # Simple comma-separated list or single node
            nodes = [n.strip() for n in node_list.split(',')]
        
        # Distribute GPUs across nodes (assume equal distribution)
        gpus_per_node = gpu_count // len(nodes) if nodes else gpu_count
        remainder = gpu_count % len(nodes) if nodes else 0
        
        for idx, node in enumerate(nodes):
            # Give extra GPU to first nodes if there's a remainder
            node_gpu_count = gpus_per_node + (1 if idx < remainder else 0)
            
            if node not in job_mapping:
                job_mapping[node] = []
            job_mapping[node].append((job_id, gpu_type, node_gpu_count))
    
    return job_mapping



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


def display_nodes(nodes, slots=8, show_job_ids=True):
    """
    Display node information in a table format, including detailed info and a
    GPU usage graph with job IDs.
    """
    if not nodes:
        print("No node information to display.")
        return

    # Get job-to-GPU mapping
    job_mapping = get_job_gpu_mapping() if show_job_ids else {}
    
    # Determine max GPU slots for the table
    max_slots = max([n.get("GPUTot", 0) for n in nodes] + [slots])
    
    # Define table headers
    titles = ["NodeName", "State", "Partitions", "CPUs", "Memory", "GPUs"]
    # Add column headers for each GPU slot
    for i in range(max_slots):
        titles.append(f" #{i+1} ")
    
    # Add %CPU column at the end
    titles.append("%CPU")

    rows = []
    for node in nodes:
        node_name = node["NodeName"]
        
        # Format text-based GPU information
        gpu_alloc = node.get("GPUAlloc", 0)
        gpu_total = node.get("GPUTot", 0)
        gpu_details = node.get("GPUDetails", "")
        cpu_load = node.get("CPULoad", 0.0)
        
        if gpu_total > 0:
            gpu_info = f"{gpu_alloc}/{gpu_total}"
            if gpu_details:
                gpu_info += f" ({gpu_details})"
        else:
            gpu_info = "N/A"
        
        # Build GPU slot visualization using node's GPU allocation by type
        gpu_slots = []
        gpu_alloc_by_type = node.get("GPUAllocByType", {})
        
        if gpu_alloc_by_type:
            # Build slot assignments from allocated GPU types
            slot_assignments = []
            for gpu_type, count in gpu_alloc_by_type.items():
                # Use first 4 characters of GPU type
                gpu_abbrev = gpu_type[:4] if len(gpu_type) >= 4 else gpu_type
                for _ in range(count):
                    slot_assignments.append(gpu_abbrev)
            
            # Fill GPU slots
            for i in range(max_slots):
                if i < len(slot_assignments):
                    # Show GPU type abbreviation in this slot
                    gpu_slots.append(slot_assignments[i])
                elif i < gpu_total:
                    # Available but unused GPU
                    gpu_slots.append("")
                else:
                    # No GPU slot
                    gpu_slots.append("")
        else:
            # Fallback to simple # visualization if no GPU type info
            used = min(gpu_alloc, gpu_total)
            for i in range(max_slots):
                if i < used:
                    gpu_slots.append("#")
                elif i < gpu_total:
                    gpu_slots.append("")
                else:
                    gpu_slots.append("")

        
        # Ensure we have exactly max_slots elements
        while len(gpu_slots) < max_slots:
            gpu_slots.append("")
        
        # Format CPU load percentage
        cpu_load_str = f"{cpu_load:.2f}"
        
        rows.append([
            node_name,
            color_state(node["State"]),
            node["Partitions"],
            node["CPUs"],
            node["Memory"],
            gpu_info,
            *gpu_slots[:max_slots],
            cpu_load_str
        ])

    table = AsciiTable([titles] + rows)
    for i in range(len(titles)):
        table.justify_columns[i] = "left"
    table.justify_columns[0] = "right"

    output = table.table
    print(output)
    return output



def show_job_detail(job_id):
    """
    Show detailed GPU usage information for a specific job.
    """
    job_mapping = get_job_gpu_mapping()
    
    # Find which nodes this job is running on
    nodes_with_job = []
    for node_name, jobs in job_mapping.items():
        for jid, gpu_type, gpu_count in jobs:
            if str(jid) == str(job_id):
                nodes_with_job.append((node_name, gpu_count))
    
    if not nodes_with_job:
        print(f"Job {job_id} not found or not using GPUs.")
        return
    
    print(colored(f"Job ID: {job_id}", "cyan", attrs=["bold"]))
    print(colored("=" * 60, "cyan"))
    print()
    
    # Get job details from squeue
    try:
        result = subprocess.check_output(
            ["squeue", "-j", str(job_id), "-h", "-o", "%i|%j|%u|%T|%M|%l|%b"],
            text=True,
            stderr=subprocess.PIPE
        ).strip()
        
        if result:
            parts = result.split('|')
            if len(parts) >= 7:
                job_name = parts[1].strip()
                user = parts[2].strip()
                state = parts[3].strip()
                runtime = parts[4].strip()
                timelimit = parts[5].strip()
                gres = parts[6].strip()
                
                print(f"  Job Name:   {colored(job_name, 'yellow')}")
                print(f"  User:       {user}")
                print(f"  State:      {colored(state, 'green' if state == 'RUNNING' else 'yellow')}")
                print(f"  Runtime:    {runtime}")
                print(f"  Time Limit: {timelimit}")
                print(f"  GRES:       {gres}")
                print()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    
    # Show GPU allocation details
    print(colored("GPU Allocation:", "yellow", attrs=["bold"]))
    print()
    
    total_gpus = sum(gpu_count for _, gpu_count in nodes_with_job)
    print(f"  Total GPUs: {colored(str(total_gpus), 'green', attrs=['bold'])}")
    print()
    
    # Show per-node allocation
    titles = ["Node", "GPUs Allocated"]
    rows = []
    for node_name, gpu_count in nodes_with_job:
        rows.append([node_name, str(gpu_count)])
    
    table = AsciiTable([titles] + rows)
    table.justify_columns[0] = "left"
    table.justify_columns[1] = "center"
    print(table.table)


def main():
    """
    Entry point for the 'winfo' command.
    """
    parser = argparse.ArgumentParser(
        description="Display SLURM node information with GPU usage and job IDs."
    )
    parser.add_argument(
        "--include-down",
        action="store_true",
        help="Include nodes in 'down' or 'drain' states."
    )
    parser.add_argument(
        "--graph",
        action="store_true",
        help="Formerly used to toggle graph view. Now the merged view is default."
    )
    parser.add_argument(
        "--slots",
        type=int,
        default=8,
        help="Minimum number of GPU slots to display (default: 8)."
    )
    parser.add_argument(
        "--job",
        type=str,
        help="Show detailed GPU usage for a specific job ID."
    )
    args = parser.parse_args()

    try:
        if args.job:
            # Show detailed information for a specific job
            show_job_detail(args.job)
        else:
            # Show node information table
            nodes = get_node_info(include_down=args.include_down)
            display_nodes(nodes, slots=args.slots)
    except RuntimeError as e:
        print(f"Error: {e}")

