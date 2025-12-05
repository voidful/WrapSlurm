from termcolor import colored

def main():
    print(colored("WrapSlurm - Helper Commands Summary", "green", attrs=["bold"]))
    print("-" * 50)
    
    commands = [
        ("wr", "Run/Submit jobs (Smart wrapper for sbatch)", "wr [script] [flags]"),
        ("wl", "Log monitor (Tail latest job log)", "wl [flags]"),
        ("wk", "Kill/Cancel jobs (Smart wrapper for scancel)", "wk [job_id] [flags]"),
        ("wq", "Queue view (Prettified squeue)", "wq"),
        ("wi", "Info/Nodes view (sinfo wrapper)", "wi"),
        ("ws", "Show this help message", "ws")
    ]

    for cmd, desc, usage in commands:
        print(f"{colored(cmd, 'cyan', attrs=['bold'])} : {desc}")
        print(f"     Usage: {usage}")
        print()

    print("-" * 50)
    print("Run any command with --help for more details. (e.g., wr --help)")

if __name__ == "__main__":
    main()
