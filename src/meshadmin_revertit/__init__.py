"""
MeshAdminRevertIt - Timed confirmation system for Linux configuration changes.

This module provides automatic reversion of system configuration changes
if not confirmed within a specified timeout period. Designed for remote
system administrators to prevent loss of access due to configuration errors.
"""

__version__ = "1.0.0"
__author__ = "MeshAdmin"
__email__ = "admin@meshadmin.com"

from .daemon.main import MeshAdminDaemon
from .snapshot.manager import SnapshotManager
from .monitor.watcher import ConfigurationMonitor
from .timeout.manager import TimeoutManager
from .revert.engine import RevertEngine

__all__ = [
    "MeshAdminDaemon",
    "SnapshotManager", 
    "ConfigurationMonitor",
    "TimeoutManager",
    "RevertEngine"
]