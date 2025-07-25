#!/usr/bin/env python3
"""
MeshAdminRevertIt - Timed confirmation system for Linux configuration changes
Automatically reverts system changes if not confirmed within timeout period.
"""

from setuptools import setup, find_packages
import os

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="meshadmin-revertit",
    version="1.0.0",
    author="MeshAdmin",
    description="Timed confirmation system for Linux configuration changes with automatic revert",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: System :: Systems Administration",
        "Topic :: System :: Networking",
    ],
    python_requires=">=3.8",
    install_requires=[
        "psutil>=5.8.0",
        "watchdog>=2.1.0",
        "pyyaml>=6.0",
        "croniter>=1.3.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=22.0.0",
            "flake8>=5.0.0",
            "mypy>=1.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "meshadmin-revertit=meshadmin_revertit.cli.main:main",
            "meshadmin-daemon=meshadmin_revertit.daemon.main:main",
        ],
    },
    include_package_data=True,
    package_data={
        "meshadmin_revertit": [
            "config/*.yaml",
            "systemd/*.service",
        ],
    },
)