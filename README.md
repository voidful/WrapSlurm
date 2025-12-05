# WrapSlurm

WrapSlurm is a powerful and user-friendly wrapper for SLURM job management, designed to simplify job submission, resource querying, log monitoring, and cancellation in SLURM environments. With a suite of commands like `wrun`, `wlog`, `wqueue`, `winfo`, and `wk`, WrapSlurm enhances productivity for researchers and engineers working in high-performance computing (HPC) clusters.

---

## Features

- **Simplified Job Submission (`wr`)**:
  - Automatically detect optimal resources (nodes, partitions, CPUs, memory, GPUs) based on the cluster's configuration.
  - Friendly summaries before each run highlight auto-detected values and log locations.
  - Persist preferred defaults (e.g., partition, account, log directory) with `--save-defaults`.
  - Automatically use the partition's maximum runtime when no explicit `--time` is provided.
  - Support for interactive and non-interactive SLURM jobs, plus a convenient `--dry-run` preview mode.
  - Customizable SLURM settings like time, tasks per node, exclusions, job names, and output directories.

- **Log Monitoring (`wl`)**:
  - Watch real-time SLURM logs for specific job IDs or the latest job.
- **Job Cancellation (`wk`)**:
  - Quickly terminate jobs (optionally with a signal) using a friendly wrapper around `scancel`.

- **Queue Visualization (`wq`)**:
  - View and analyze job queues in a prettified table format with color-coded states.

- **Node Resource Querying (`wi`)**:
  - Display detailed SLURM node information, including memory, CPU, and GPU usage.

- **Help / Usage (`ws`)**:
  - Display a summary of all WrapSlurm commands and their usage.

---

## Installation

WrapSlurm is available on PyPI and can be installed using pip:

```bash
pip install wrapslurm
```

### Post-Installation Notes

If the scripts `wrun`, `wlog`, `wqueue`, `winfo`, and `wk` are installed in a directory not included in your system's `PATH` (e.g., `~/.local/bin`), you may need to update your `PATH` environment variable:

1. Add the following line to your shell configuration file (`~/.bashrc` or `~/.zshrc`):

   ```bash
   export PATH="$PATH:$HOME/.local/bin"
   ```

2. Reload your shell:

   ```bash
   source ~/.bashrc  # or source ~/.zshrc
   ```

---

## Usage

### 1. **Submit a Job (`wrun`)**

#### Basic Usage:
Submit a script with auto-detected resources:

```bash
wr ./train_script.py --epochs 10
```
`wr` now shows a colorized summary of the resources that will be requested, including values auto-detected from `sinfo` and those loaded from saved defaults.

`wr` now shows a colorized summary of the resources that will be requested, including values auto-detected from `sinfo` and those loaded from saved defaults.

#### Specify Resources:
Submit a job with explicit resources:

```bash
wr --nodes 2 --partition gp4d --account ENT212162 --cpus-per-task 8 --memory 200G --gpus 4 ./train_script.py
```

You can also name the job, change where helper scripts are stored, or choose a custom log directory:

```bash
wr --job-name my-training --script-dir ./sbatch --report-dir ./logs python train.py
```

#### Interactive Mode:
Start an interactive session:

```bash
wr
```

Use `wr --interactive --nodes 2` to override the automatic detection while still launching an interactive shell.

#### Save Your Defaults:

You can persist frequently used settings (e.g., partition, account, log directory) so future runs pick them up automatically:

```bash
wr --save-defaults --partition gp4d --account ENT212162 --report-dir ./slurm-report
```

Defaults are stored in `~/.config/wrapslurm/defaults.json`. Running `wr --save-defaults` stores the provided flags and exits without submitting a job.

#### Full Help:
View all available options:

```bash
wr --help
```

#### Preview the Generated Script:

```bash
wr --dry-run python train.py
```

Dry runs print the exact `sbatch` script so you can review the environment setup before submitting.

---

### 2. **Monitor Logs (`wlog`)**

`wlog` streams SLURM output with `tail -n 20 -f` so you can follow job progress without the extra load from `watch`.

Logs are written to `./slurm-report/%j.out` and `./slurm-report/%j.err` by default.

#### Watch the Latest Log File:
```bash
wl
```

#### Watch Logs for a Specific Job ID:
```bash
wl --job-id 12345678
```

To inspect stderr instead, open `./slurm-report/12345678.err` with your preferred tool.

---

### 3. **Cancel a Job (`wk`)**

Send `scancel` commands without memorizing flags:

```bash
wk 12345678
```

Cancel multiple jobs in one go:

```bash
wk 12345678 12345679
```

Pass through additional options such as a signal or user scope:

```bash
wk 12345678 --signal SIGINT
wk --user alice 12345680
```

All options are forwarded to `scancel`, so you can combine them as needed.

---

### 4. **View Job Queue (`wqueue`)**

Display the job queue in a table format:

```bash
wqueue
```

---

### 5. **Query Node Resources (`winfo`)**

#### Basic Usage:
```bash
winfo
```

#### Include Down or Drained Nodes:
```bash
winfo --include-down
```

#### Display GPU Usage Graph:
```bash
winfo --graph
```

---

## Example Workflow

1. Query available resources:
   ```bash
   wi
   ```

2. Submit a job:
   ```bash
   wr --account xxxxxx --time 2-00:00:00 ./train_script.py
   ```

3. Monitor job logs:
   ```bash
   wl
   ```

4. Check the queue:
   ```bash
   wq
   ```

---

## Development

### Cloning the Repository

```bash
git clone https://github.com/yourusername/wrapslurm.git
cd wrapslurm
```

### Install Dependencies

Install the required Python packages:

```bash
pip install -r requirements.txt
```

### Run Tests

Execute unit tests:

```bash
pytest
```

---

## Contributing

We welcome contributions! Please follow these steps:

1. Fork the repository.
2. Create a feature branch:
   ```bash
   git checkout -b feature-name
   ```
3. Commit your changes:
   ```bash
   git commit -m "Add feature-name"
   ```
4. Push to your fork:
   ```bash
   git push origin feature-name
   ```
5. Submit a pull request.

---

## License

This project is licensed under the [MIT License](LICENSE).

---


## Acknowledgments

Special thanks to the SLURM community for making HPC resource management accessible to researchers worldwide.

---