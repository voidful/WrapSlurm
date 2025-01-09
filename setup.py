import os
from setuptools import setup, find_packages
LOCAL_BIN_DIR = os.path.expanduser("~/.local/bin")

setup(
    name="WrapSlurm",
    version="0.0.6",
    description="A utility for managing SLURM jobs and nodes with enhanced display features.",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Voidful",
    author_email="voidful@eric-lam.com",
    url="https://github.com/voidful/WrapSlurm",
    license="MIT",
    packages=find_packages(),
    install_requires=[
        "terminaltables",
        "termcolor",
    ],
    python_requires=">=3.6",
    entry_points={
        "console_scripts": [
            "winfo = wrapslurm.node_info:main",
            "wqueue = wrapslurm.queue_info:main",
            "wrun = wrapslurm.job_runner:main",
            "wlog = wrapslurm.track_job:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)

if LOCAL_BIN_DIR not in os.environ["PATH"]:
    warning_message = f"""
    WARNING: The scripts winfo, wlog, wqueue, and wrun are installed in '{LOCAL_BIN_DIR}',
    which is not currently in your PATH.

    To use these commands globally, add the following line to your shell configuration file (e.g., ~/.bashrc or ~/.zshrc):

        export PATH="$PATH:{LOCAL_BIN_DIR}"

    Then, reload your shell:

        source ~/.bashrc  # or source ~/.zshrc
    """
    print(warning_message)