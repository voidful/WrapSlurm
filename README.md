# WrapSlurm

WrapSlurm is a powerful and user-friendly wrapper for SLURM job management, designed to simplify job submission, resource querying, and log monitoring in SLURM environments. With a suite of commands like `wrun`, `wlog`, `wqueue`, and `winfo`, WrapSlurm enhances productivity for researchers and engineers working in high-performance computing (HPC) clusters.

---

## Features

- **Simplified Job Submission (`wr`)**:
  - Automatically detect optimal resources (nodes, partitions, CPUs, memory, GPUs) based on the cluster's configuration.
  - Support for interactive and non-interactive SLURM jobs.
  - Customizable SLURM settings like time, tasks per node, and exclusions.

- **Log Monitoring (`wl`)**:
  - Watch real-time SLURM logs for specific job IDs or the latest job.

- **Queue Visualization (`wq`)**:
  - View and analyze job queues in a prettified table format with color-coded states.

- **Node Resource Querying (`wi`)**:
  - Display detailed SLURM node information, including memory, CPU, and GPU usage.

---

## Installation

WrapSlurm is available on PyPI and can be installed using pip:

```bash
pip install wrapslurm
```

### Post-Installation Notes

If the scripts `wrun`, `wlog`, `wqueue`, and `winfo` are installed in a directory not included in your system's `PATH` (e.g., `~/.local/bin`), you may need to update your `PATH` environment variable:

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
wr ./train_script.py
```

#### Specify Resources:
Submit a job with explicit resources:

```bash
wr --nodes 2 --partition gp4d --account ENT212162 --cpus-per-task 8 --memory 200G --gpus 4 ./train_script.py
```

#### Interactive Mode:
Start an interactive session:

```bash
wr
```

#### Full Help:
View all available options:

```bash
wr --help
```

---

### 2. **Monitor Logs (`wlog`)**

#### Watch the Latest Log File:
```bash
wl
```

#### Watch Logs for a Specific Job ID:
```bash
wl --job-id 12345678
```

---

### 3. **View Job Queue (`wqueue`)**

Display the job queue in a table format:

```bash
wqueue
```

---

### 4. **Query Node Resources (`winfo`)**

#### Basic Usage:
```bash
winfo
```

#### Include Down or Drained Nodes:
```bash
winfo --include-down
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