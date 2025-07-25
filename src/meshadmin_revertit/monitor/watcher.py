#!/usr/bin/env python3
"""
Configuration Monitor - Watches for changes in critical system configuration files.
"""

import os
import time
import logging
import fnmatch
from pathlib import Path
from typing import Dict, List, Any, Set, Optional, Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent


class ConfigurationMonitor:
    """Monitors critical system configuration files for changes."""
    
    def __init__(self, config: Dict[str, Any], timeout_manager, snapshot_manager):
        """Initialize configuration monitor."""
        self.config = config
        self.timeout_manager = timeout_manager
        self.snapshot_manager = snapshot_manager
        self.logger = logging.getLogger(__name__)
        
        self.observer = Observer()
        self.watched_paths: Set[str] = set()
        self.running = False
        
        # Get all paths to monitor
        self.monitor_paths = self._collect_monitor_paths()
        
        self.logger.info(f"Configuration monitor initialized with {len(self.monitor_paths)} paths")
    
    def _collect_monitor_paths(self) -> List[str]:
        """Collect all paths that should be monitored."""
        all_paths = []
        
        # Network configuration files
        all_paths.extend(self.config.get('network_configs', []))
        
        # SSH configuration files
        all_paths.extend(self.config.get('ssh_configs', []))
        
        # Firewall configuration files
        all_paths.extend(self.config.get('firewall_configs', []))
        
        # System service files
        all_paths.extend(self.config.get('service_configs', []))
        
        # Custom paths
        all_paths.extend(self.config.get('custom_paths', []))
        
        # Expand glob patterns and filter existing paths
        expanded_paths = []
        for path_pattern in all_paths:
            if '*' in path_pattern or '?' in path_pattern:
                # Handle glob patterns
                expanded = self._expand_glob_pattern(path_pattern)
                expanded_paths.extend(expanded)
            else:
                # Direct path
                if os.path.exists(path_pattern):
                    expanded_paths.append(path_pattern)
                else:
                    self.logger.debug(f"Monitor path does not exist: {path_pattern}")
        
        return expanded_paths
    
    def _expand_glob_pattern(self, pattern: str) -> List[str]:
        """Expand glob patterns to actual file paths."""
        import glob
        
        try:
            matches = glob.glob(pattern, recursive=True)
            existing_matches = [m for m in matches if os.path.exists(m)]
            self.logger.debug(f"Glob pattern '{pattern}' expanded to {len(existing_matches)} files")
            return existing_matches
        except Exception as e:
            self.logger.warning(f"Failed to expand glob pattern '{pattern}': {e}")
            return []
    
    def start_monitoring(self) -> None:
        """Start monitoring configuration files."""
        if self.running:
            self.logger.warning("Configuration monitor is already running")
            return
        
        self.logger.info("Starting configuration monitoring")
        self.running = True
        
        # Set up file system watchers
        self._setup_watchers()
        
        # Start the observer
        self.observer.start()
        
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop_monitoring()
    
    def _setup_watchers(self) -> None:
        """Set up file system watchers for monitored paths."""
        # Group paths by directory to minimize watchers
        directories_to_watch: Dict[str, List[str]] = {}
        
        for path in self.monitor_paths:
            path_obj = Path(path)
            
            if path_obj.is_file():
                parent_dir = str(path_obj.parent)
                if parent_dir not in directories_to_watch:
                    directories_to_watch[parent_dir] = []
                directories_to_watch[parent_dir].append(path)
            elif path_obj.is_dir():
                directories_to_watch[path] = [path]
        
        # Create event handler and set up observers
        event_handler = ConfigurationEventHandler(
            monitored_files=set(self.monitor_paths),
            on_change_callback=self._handle_configuration_change
        )
        
        for directory, files in directories_to_watch.items():
            if os.path.exists(directory):
                try:
                    self.observer.schedule(event_handler, directory, recursive=True)
                    self.watched_paths.add(directory)
                    self.logger.debug(f"Watching directory: {directory} (files: {len(files)})")
                except Exception as e:
                    self.logger.error(f"Failed to watch directory {directory}: {e}")
    
    def _handle_configuration_change(self, file_path: str, event_type: str) -> None:
        """Handle configuration file change event."""
        self.logger.info(f"Configuration change detected: {file_path} ({event_type})")
        
        # Determine change category
        change_category = self._categorize_change(file_path)
        
        # Create snapshot before change (if not already exists)
        try:
            snapshot_id = self.snapshot_manager.create_snapshot(
                description=f"Pre-change snapshot for {file_path} modification"
            )
            self.logger.info(f"Created pre-change snapshot: {snapshot_id}")
        except Exception as e:
            self.logger.error(f"Failed to create pre-change snapshot: {e}")
            snapshot_id = None
        
        # Start timeout for confirmation
        try:
            self.timeout_manager.start_timeout(
                change_id=f"{change_category}_{int(time.time())}",
                file_path=file_path,
                change_category=change_category,
                snapshot_id=snapshot_id,
                event_type=event_type
            )
        except Exception as e:
            self.logger.error(f"Failed to start timeout for change: {e}")
    
    def _categorize_change(self, file_path: str) -> str:
        """Categorize the type of configuration change."""
        path_lower = file_path.lower()
        
        # Network configuration
        if any(net_path in path_lower for net_path in [
            'network', 'netplan', 'networkmanager', 'interfaces'
        ]):
            return 'network'
        
        # SSH configuration
        if 'ssh' in path_lower:
            return 'ssh'
        
        # Firewall configuration
        if any(fw_path in path_lower for fw_path in [
            'iptables', 'ufw', 'firewall', 'firewalld'
        ]):
            return 'firewall'
        
        # System services
        if 'systemd' in path_lower or file_path.endswith('.service'):
            return 'service'
        
        # Default category
        return 'system'
    
    def stop_monitoring(self) -> None:
        """Stop monitoring configuration files."""
        self.logger.info("Stopping configuration monitoring")
        self.running = False
        
        if self.observer.is_alive():
            self.observer.stop()
            self.observer.join(timeout=5)
        
        self.logger.info("Configuration monitoring stopped")
    
    def add_monitor_path(self, path: str) -> bool:
        """Add a new path to monitor."""
        if path in self.monitor_paths:
            self.logger.debug(f"Path already monitored: {path}")
            return True
        
        if not os.path.exists(path):
            self.logger.warning(f"Cannot monitor non-existent path: {path}")
            return False
        
        self.monitor_paths.append(path)
        
        # If monitoring is active, add new watcher
        if self.running:
            try:
                path_obj = Path(path)
                parent_dir = str(path_obj.parent if path_obj.is_file() else path_obj)
                
                if parent_dir not in self.watched_paths:
                    event_handler = ConfigurationEventHandler(
                        monitored_files={path},
                        on_change_callback=self._handle_configuration_change
                    )
                    self.observer.schedule(event_handler, parent_dir, recursive=True)
                    self.watched_paths.add(parent_dir)
                
                self.logger.info(f"Added monitor path: {path}")
                return True
            except Exception as e:
                self.logger.error(f"Failed to add monitor path {path}: {e}")
                return False
        
        return True
    
    def remove_monitor_path(self, path: str) -> bool:
        """Remove a path from monitoring."""
        if path not in self.monitor_paths:
            self.logger.debug(f"Path not monitored: {path}")
            return True
        
        self.monitor_paths.remove(path)
        self.logger.info(f"Removed monitor path: {path}")
        
        # Note: We don't remove the observer here as it might be watching other files
        # in the same directory. This is acceptable as the event handler will filter.
        
        return True
    
    def get_monitored_paths(self) -> List[str]:
        """Get list of currently monitored paths."""
        return self.monitor_paths.copy()
    
    def is_monitoring(self) -> bool:
        """Check if monitoring is currently active."""
        return self.running


class ConfigurationEventHandler(FileSystemEventHandler):
    """File system event handler for configuration changes."""
    
    def __init__(self, monitored_files: Set[str], on_change_callback: Callable[[str, str], None]):
        """Initialize event handler."""
        super().__init__()
        self.monitored_files = monitored_files
        self.on_change_callback = on_change_callback
        self.logger = logging.getLogger(__name__)
        
        # Track recent events to avoid duplicates
        self.recent_events: Dict[str, float] = {}
        self.event_debounce_time = 2.0  # seconds
    
    def _should_process_event(self, file_path: str) -> bool:
        """Check if event should be processed (debouncing)."""
        current_time = time.time()
        last_event_time = self.recent_events.get(file_path, 0)
        
        if current_time - last_event_time < self.event_debounce_time:
            return False
        
        self.recent_events[file_path] = current_time
        return True
    
    def _is_monitored_file(self, file_path: str) -> bool:
        """Check if file should be monitored."""
        # Direct match
        if file_path in self.monitored_files:
            return True
        
        # Check if any monitored path matches this file
        for monitored_path in self.monitored_files:
            # Handle glob patterns
            if '*' in monitored_path or '?' in monitored_path:
                if fnmatch.fnmatch(file_path, monitored_path):
                    return True
            
            # Handle directory monitoring
            elif os.path.isdir(monitored_path) and file_path.startswith(monitored_path):
                return True
        
        return False
    
    def on_modified(self, event):
        """Handle file modification events."""
        if not isinstance(event, FileModifiedEvent) or event.is_directory:
            return
        
        file_path = event.src_path
        
        if self._is_monitored_file(file_path) and self._should_process_event(file_path):
            self.logger.debug(f"File modification detected: {file_path}")
            self.on_change_callback(file_path, "modified")
    
    def on_created(self, event):
        """Handle file creation events."""
        if not isinstance(event, FileCreatedEvent) or event.is_directory:
            return
        
        file_path = event.src_path
        
        if self._is_monitored_file(file_path) and self._should_process_event(file_path):
            self.logger.debug(f"File creation detected: {file_path}")
            self.on_change_callback(file_path, "created")
    
    def on_moved(self, event):
        """Handle file move events."""
        if event.is_directory:
            return
        
        # Check both source and destination paths
        for file_path, event_type in [(event.src_path, "moved_from"), (event.dest_path, "moved_to")]:
            if self._is_monitored_file(file_path) and self._should_process_event(file_path):
                self.logger.debug(f"File move detected: {file_path} ({event_type})")
                self.on_change_callback(file_path, event_type)