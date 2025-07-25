#!/usr/bin/env python3
"""
MeshAdminRevertIt Daemon - Main daemon process for monitoring configuration changes.
"""

import os
import sys
import signal
import time
import logging
import yaml
import threading
from pathlib import Path
from typing import Optional, Dict, Any

from ..snapshot.manager import SnapshotManager
from ..monitor.watcher import ConfigurationMonitor
from ..timeout.manager import TimeoutManager
from ..revert.engine import RevertEngine
from ..distro.detector import DistroDetector


class MeshAdminDaemon:
    """Main daemon class for MeshAdminRevertIt."""
    
    def __init__(self, config_path: str = "/etc/meshadmin-revertit/config.yaml"):
        """Initialize the daemon with configuration."""
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.running = False
        self.logger: Optional[logging.Logger] = None
        
        # Core components
        self.snapshot_manager: Optional[SnapshotManager] = None
        self.config_monitor: Optional[ConfigurationMonitor] = None
        self.timeout_manager: Optional[TimeoutManager] = None
        self.revert_engine: Optional[RevertEngine] = None
        self.distro_detector: Optional[DistroDetector] = None
        
        # Threading
        self.monitor_thread: Optional[threading.Thread] = None
        self.timeout_thread: Optional[threading.Thread] = None
        
    def load_config(self) -> None:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)
        except FileNotFoundError:
            # Use default configuration if file not found
            self.config = self._get_default_config()
            self._create_default_config_file()
        except yaml.YAMLError as e:
            raise RuntimeError(f"Error parsing configuration file: {e}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'global': {
                'default_timeout': 300,
                'max_timeout': 1800,
                'min_timeout': 60,
                'log_level': 'INFO',
                'log_file': '/var/log/meshadmin-revertit.log',
                'pid_file': '/var/run/meshadmin-revertit.pid'
            },
            'snapshot': {
                'enable_timeshift': True,
                'snapshot_location': '/var/lib/meshadmin-revertit/snapshots',
                'max_snapshots': 10,
                'compress_snapshots': True
            },
            'monitoring': {
                'network_configs': [
                    '/etc/network/interfaces',
                    '/etc/netplan/*.yaml',
                    '/etc/NetworkManager/system-connections/*',
                    '/etc/systemd/network/*'
                ],
                'ssh_configs': [
                    '/etc/ssh/sshd_config',
                    '/etc/ssh/ssh_config.d/*'
                ],
                'firewall_configs': [
                    '/etc/iptables/rules.v4',
                    '/etc/iptables/rules.v6',
                    '/etc/ufw/*',
                    '/etc/firewalld/**/*'
                ],
                'service_configs': [
                    '/etc/systemd/system/*',
                    '/etc/systemd/user/*'
                ],
                'custom_paths': []
            },
            'timeout': {
                'timeout_action': 'revert',
                'connectivity_check': True,
                'connectivity_endpoints': ['8.8.8.8', '1.1.1.1', 'google.com'],
                'connectivity_timeout': 10,
                'revert_grace_period': 30
            },
            'notifications': {
                'email_enabled': False,
                'syslog_enabled': True,
                'desktop_enabled': True
            },
            'distro': {
                'auto_detect': True,
                'force_distro': None
            }
        }
    
    def _create_default_config_file(self) -> None:
        """Create default configuration file."""
        config_dir = os.path.dirname(self.config_path)
        os.makedirs(config_dir, exist_ok=True)
        
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f, default_flow_style=False, indent=2)
    
    def setup_logging(self) -> None:
        """Setup logging configuration."""
        log_level = getattr(logging, self.config['global']['log_level'].upper())
        log_file = self.config['global']['log_file']
        
        # Create log directory if it doesn't exist
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("MeshAdminRevertIt daemon starting")
    
    def write_pid_file(self) -> None:
        """Write process ID to PID file."""
        pid_file = self.config['global']['pid_file']
        pid_dir = os.path.dirname(pid_file)
        os.makedirs(pid_dir, exist_ok=True)
        
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
    
    def remove_pid_file(self) -> None:
        """Remove PID file."""
        pid_file = self.config['global']['pid_file']
        try:
            os.unlink(pid_file)
        except FileNotFoundError:
            pass
    
    def initialize_components(self) -> None:
        """Initialize all daemon components."""
        self.logger.info("Initializing daemon components")
        
        # Initialize distro detector
        self.distro_detector = DistroDetector(self.config['distro'])
        distro_info = self.distro_detector.detect()
        self.logger.info(f"Detected distribution: {distro_info}")
        
        # Initialize snapshot manager
        self.snapshot_manager = SnapshotManager(
            config=self.config['snapshot'],
            distro_info=distro_info
        )
        
        # Initialize revert engine
        self.revert_engine = RevertEngine(
            snapshot_manager=self.snapshot_manager,
            config=self.config,
            distro_info=distro_info
        )
        
        # Initialize timeout manager
        self.timeout_manager = TimeoutManager(
            config=self.config['timeout'],
            revert_engine=self.revert_engine
        )
        
        # Initialize configuration monitor
        self.config_monitor = ConfigurationMonitor(
            config=self.config['monitoring'],
            timeout_manager=self.timeout_manager,
            snapshot_manager=self.snapshot_manager
        )
        
        self.logger.info("All components initialized successfully")
    
    def start_monitoring_threads(self) -> None:
        """Start monitoring threads."""
        self.logger.info("Starting monitoring threads")
        
        # Start configuration monitor thread
        self.monitor_thread = threading.Thread(
            target=self.config_monitor.start_monitoring,
            daemon=True
        )
        self.monitor_thread.start()
        
        # Start timeout manager thread
        self.timeout_thread = threading.Thread(
            target=self.timeout_manager.start_processing,
            daemon=True
        )
        self.timeout_thread.start()
        
        self.logger.info("Monitoring threads started")
    
    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, shutting down gracefully")
            self.stop()
        
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    
    def start(self) -> None:
        """Start the daemon."""
        try:
            # Load configuration
            self.load_config()
            
            # Setup logging
            self.setup_logging()
            
            # Write PID file
            self.write_pid_file()
            
            # Setup signal handlers
            self.setup_signal_handlers()
            
            # Initialize components
            self.initialize_components()
            
            # Start monitoring threads
            self.start_monitoring_threads()
            
            self.running = True
            self.logger.info("MeshAdminRevertIt daemon started successfully")
            
            # Main daemon loop
            while self.running:
                time.sleep(1)
                
        except Exception as e:
            if self.logger:
                self.logger.critical(f"Critical error in daemon: {e}")
            else:
                print(f"Critical error in daemon: {e}", file=sys.stderr)
            self.stop()
            sys.exit(1)
    
    def stop(self) -> None:
        """Stop the daemon."""
        self.running = False
        
        if self.logger:
            self.logger.info("Stopping MeshAdminRevertIt daemon")
        
        # Stop components
        if self.config_monitor:
            self.config_monitor.stop_monitoring()
        
        if self.timeout_manager:
            self.timeout_manager.stop_processing()
        
        # Wait for threads to finish
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        
        if self.timeout_thread and self.timeout_thread.is_alive():
            self.timeout_thread.join(timeout=5)
        
        # Remove PID file
        self.remove_pid_file()
        
        if self.logger:
            self.logger.info("MeshAdminRevertIt daemon stopped")


def main():
    """Main entry point for the daemon."""
    import argparse
    
    parser = argparse.ArgumentParser(description="MeshAdminRevertIt Daemon")
    parser.add_argument(
        "--config", 
        default="/etc/meshadmin-revertit/config.yaml",
        help="Configuration file path"
    )
    parser.add_argument(
        "--foreground", 
        action="store_true",
        help="Run in foreground (don't daemonize)"
    )
    
    args = parser.parse_args()
    
    daemon = MeshAdminDaemon(config_path=args.config)
    
    if not args.foreground:
        # Daemonize process
        if os.fork() > 0:
            sys.exit(0)
        
        os.setsid()
        
        if os.fork() > 0:
            sys.exit(0)
        
        # Redirect standard file descriptors
        sys.stdin.close()
        sys.stdout.close()
        sys.stderr.close()
    
    daemon.start()


if __name__ == "__main__":
    main()