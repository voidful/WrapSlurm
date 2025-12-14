from setuptools import setup, find_packages

setup(
    name="WrapSlurm",
    version="0.1.0",
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
        "questionary",
    ],
    python_requires=">=3.6",
    entry_points={
        "console_scripts": [
            "wi = wrapslurm.node_info:main",
            "wq = wrapslurm.queue_info:main",
            "wr = wrapslurm.job_runner:main",
            "wl = wrapslurm.track_job:main",
            "wk = wrapslurm.cancel_job:main",
            "ws = wrapslurm.main_help:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
