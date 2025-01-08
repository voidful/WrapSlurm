import subprocess
import getpass
import grp
from terminaltables import AsciiTable
from termcolor import colored
import os

MAX_NAME_LENGTH = 30  # Maximum length for the job name


def truncate_name(name, max_length):
    """
    Truncate the job name if it exceeds the maximum length.
    Append '...' to indicate truncation.
    """
    if len(name) > max_length:
        return name[:max_length - 3] + "..."
    return name


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
        raise RuntimeError(f"Error retrieving user or group information: {e}")

    # Execute the `squeue` command and format the output for parsing
    cmd = ['squeue', '--noheader', '-o', '%i|%P|%j|%u|%T|%M|%D|%R']
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.PIPE, text=True).strip()
    except FileNotFoundError:
        raise RuntimeError("Command 'squeue' not found. Please ensure SLURM is installed and added to PATH.")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Error while executing squeue: {e.stderr.strip()}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error while executing squeue: {e}")

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
            print(f"Skipping incomplete line: {line}")
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


def main():
    """
    Main entry point for the `wqueue` command.
    """
    try:
        show_squeue()
    except RuntimeError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")



