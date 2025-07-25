#!/usr/bin/env python3
"""
MeshAdminRevertIt CLI - Command-line interface for managing the system.
"""

import sys
import argparse
import logging
import yaml
from pathlib import Path
from typing import Dict, Any, List

from ..daemon.main import MeshAdminDaemon
from ..snapshot.manager import SnapshotManager
from ..timeout.manager import TimeoutManager
from ..distro.detector import DistroDetector


class MeshAdminCLI:
    """Command-line interface for MeshAdminRevertIt."""
    
    def __init__(self):
        """Initialize CLI."""
        self.config_path = "/etc/meshadmin-revertit/config.yaml"
        self.logger = None
        
    def setup_logging(self, verbose: bool = False) -> None:
        """Setup logging for CLI operations."""
        level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=level,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration file."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Configuration file not found: {self.config_path}")
            return {}
        except yaml.YAMLError as e:
            print(f"Error parsing configuration: {e}")
            return {}
    
    def cmd_status(self, args) -> int:
        """Show daemon and system status."""
        config = self.load_config()
        
        print("MeshAdminRevertIt Status")
        print("=" * 40)
        
        # Check daemon status
        pid_file = config.get('global', {}).get('pid_file', '/var/run/meshadmin-revertit.pid')
        if Path(pid_file).exists():
            try:
                with open(pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                # Check if process is running
                try:
                    import os
                    os.kill(pid, 0)
                    print(f"✓ Daemon running (PID: {pid})")
                except OSError:
                    print("✗ Daemon not running (stale PID file)")
            except Exception as e:
                print(f"✗ Error reading PID file: {e}")
        else:
            print("✗ Daemon not running")
        
        # Distribution info
        try:
            distro_detector = DistroDetector(config.get('distro', {}))
            distro_info = distro_detector.detect()
            print(f"✓ Distribution: {distro_info['name']} {distro_info['version']}")
            print(f"  Family: {distro_info['family']}")
            print(f"  Package Manager: {distro_info['package_manager']}")
            print(f"  Init System: {distro_info['init_system']}")
        except Exception as e:
            print(f"✗ Error detecting distribution: {e}")
        
        # Configuration file
        if Path(self.config_path).exists():
            print(f"✓ Configuration: {self.config_path}")
        else:
            print(f"✗ Configuration file missing: {self.config_path}")
        
        # Log file
        log_file = config.get('global', {}).get('log_file', '/var/log/meshadmin-revertit.log')
        if Path(log_file).exists():
            print(f"✓ Log file: {log_file}")
        else:
            print(f"✗ Log file not found: {log_file}")
        
        return 0
    
    def cmd_start(self, args) -> int:
        """Start the daemon."""
        if args.config:
            self.config_path = args.config
        
        try:
            daemon = MeshAdminDaemon(config_path=self.config_path)
            print("Starting MeshAdminRevertIt daemon...")
            daemon.start()
            return 0
        except Exception as e:
            print(f"Failed to start daemon: {e}")
            return 1
    
    def cmd_stop(self, args) -> int:
        """Stop the daemon."""
        config = self.load_config()
        pid_file = config.get('global', {}).get('pid_file', '/var/run/meshadmin-revertit.pid')
        
        if not Path(pid_file).exists():
            print("Daemon is not running")
            return 0
        
        try:
            with open(pid_file, 'r') as f:
                pid = int(f.read().strip())
            
            import os
            import signal
            os.kill(pid, signal.SIGTERM)
            print(f"Sent stop signal to daemon (PID: {pid})")
            return 0
            
        except Exception as e:
            print(f"Failed to stop daemon: {e}")
            return 1
    
    def cmd_restart(self, args) -> int:
        """Restart the daemon."""
        print("Stopping daemon...")
        self.cmd_stop(args)
        
        import time
        time.sleep(2)
        
        print("Starting daemon...")
        return self.cmd_start(args)
    
    def cmd_snapshots(self, args) -> int:
        """Manage snapshots."""
        config = self.load_config()
        
        try:
            # Initialize components needed for snapshot management
            distro_detector = DistroDetector(config.get('distro', {}))
            distro_info = distro_detector.detect()
            
            snapshot_manager = SnapshotManager(
                config=config.get('snapshot', {}),
                distro_info=distro_info
            )
            
            if args.snapshot_action == 'list':
                return self._list_snapshots(snapshot_manager)
            elif args.snapshot_action == 'create':
                return self._create_snapshot(snapshot_manager, args.description)
            elif args.snapshot_action == 'delete':
                return self._delete_snapshot(snapshot_manager, args.snapshot_id)
            elif args.snapshot_action == 'restore':
                return self._restore_snapshot(snapshot_manager, args.snapshot_id)
            else:
                print(f"Unknown snapshot action: {args.snapshot_action}")
                return 1
                
        except Exception as e:
            print(f"Snapshot operation failed: {e}")
            return 1
    
    def _list_snapshots(self, snapshot_manager: SnapshotManager) -> int:
        """List all snapshots."""
        snapshots = snapshot_manager.list_snapshots()
        
        if not snapshots:
            print("No snapshots found")
            return 0
        
        print("Available Snapshots:")
        print("-" * 80)
        print(f"{'ID':<30} {'Type':<10} {'Timestamp':<20} {'Description'}")
        print("-" * 80)
        
        for snapshot in snapshots:
            print(f"{snapshot['id']:<30} {snapshot['type']:<10} "
                  f"{snapshot.get('timestamp', 'unknown'):<20} "
                  f"{snapshot.get('description', 'No description')}")
        
        return 0
    
    def _create_snapshot(self, snapshot_manager: SnapshotManager, description: str = None) -> int:
        """Create a new snapshot."""
        try:
            if not description:
                description = "Manual snapshot created via CLI"
            
            snapshot_id = snapshot_manager.create_snapshot(description)
            print(f"Created snapshot: {snapshot_id}")
            return 0
        except Exception as e:
            print(f"Failed to create snapshot: {e}")
            return 1
    
    def _delete_snapshot(self, snapshot_manager: SnapshotManager, snapshot_id: str) -> int:
        """Delete a snapshot."""
        if not snapshot_id:
            print("Snapshot ID is required for deletion")
            return 1
        
        try:
            success = snapshot_manager.delete_snapshot(snapshot_id)
            if success:
                print(f"Deleted snapshot: {snapshot_id}")
                return 0
            else:
                print(f"Failed to delete snapshot: {snapshot_id}")
                return 1
        except Exception as e:
            print(f"Error deleting snapshot: {e}")
            return 1
    
    def _restore_snapshot(self, snapshot_manager: SnapshotManager, snapshot_id: str) -> int:
        """Restore from a snapshot."""
        if not snapshot_id:
            print("Snapshot ID is required for restoration")
            return 1
        
        print(f"WARNING: This will restore system configuration from snapshot: {snapshot_id}")
        response = input("Are you sure you want to continue? (yes/no): ")
        
        if response.lower() not in ['yes', 'y']:
            print("Restoration cancelled")
            return 0
        
        try:
            success = snapshot_manager.restore_snapshot(snapshot_id)
            if success:
                print(f"Successfully restored from snapshot: {snapshot_id}")
                print("You may need to restart affected services manually")
                return 0
            else:
                print(f"Failed to restore from snapshot: {snapshot_id}")
                return 1
        except Exception as e:
            print(f"Error restoring snapshot: {e}")
            return 1
    
    def cmd_timeouts(self, args) -> int:
        """Manage active timeouts."""
        config = self.load_config()
        
        try:
            # This is a simplified version - in real usage, we'd connect to the daemon
            print("Active Timeouts:")
            print("(This would connect to the running daemon to show active timeouts)")
            print("Feature requires daemon integration for full functionality")
            return 0
        except Exception as e:
            print(f"Failed to list timeouts: {e}")
            return 1
    
    def cmd_confirm(self, args) -> int:
        """Confirm a configuration change."""
        if not args.change_id:
            print("Change ID is required")
            return 1
        
        try:
            # This would connect to the daemon to confirm the change
            print(f"Confirming change: {args.change_id}")
            print("(This feature requires daemon integration)")
            return 0
        except Exception as e:
            print(f"Failed to confirm change: {e}")
            return 1
    
    def cmd_test(self, args) -> int:
        """Test system compatibility and configuration."""
        config = self.load_config()
        
        print("MeshAdminRevertIt System Test")
        print("=" * 40)
        
        # Test distribution detection
        try:
            distro_detector = DistroDetector(config.get('distro', {}))
            distro_info = distro_detector.detect()
            compatibility = distro_detector.get_compatibility_info()
            
            print(f"✓ Distribution detected: {distro_info['name']}")
            print(f"  Supported: {'Yes' if distro_detector.is_supported() else 'No'}")
            print(f"  TimeShift compatible: {'Yes' if compatibility['timeshift_available'] else 'No'}")
        except Exception as e:
            print(f"✗ Distribution detection failed: {e}")
        
        # Test snapshot capability
        try:
            snapshot_manager = SnapshotManager(
                config=config.get('snapshot', {}),
                distro_info=distro_info
            )
            
            # Try to create and delete a test snapshot
            test_snapshot = snapshot_manager.create_snapshot("Test snapshot - will be deleted")
            print("✓ Snapshot creation works")
            
            snapshot_manager.delete_snapshot(test_snapshot)
            print("✓ Snapshot deletion works")
            
        except Exception as e:
            print(f"✗ Snapshot functionality failed: {e}")
        
        # Test configuration file monitoring paths
        monitor_config = config.get('monitoring', {})
        all_paths = []
        all_paths.extend(monitor_config.get('network_configs', []))
        all_paths.extend(monitor_config.get('ssh_configs', []))
        all_paths.extend(monitor_config.get('firewall_configs', []))
        all_paths.extend(monitor_config.get('service_configs', []))
        
        existing_paths = []
        for path in all_paths:
            if '*' not in path and Path(path).exists():
                existing_paths.append(path)
        
        print(f"✓ Found {len(existing_paths)} existing configuration files to monitor")
        
        # Test permissions
        try:
            import os
            if os.geteuid() != 0:
                print("⚠ Warning: Not running as root - some features may not work")
            else:
                print("✓ Running with root privileges")
        except Exception:
            print("? Could not determine privilege level")
        
        return 0


def main():
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="MeshAdminRevertIt - Timed confirmation system for Linux configuration changes"
    )
    
    parser.add_argument(
        '--config', 
        default='/etc/meshadmin-revertit/config.yaml',
        help='Configuration file path'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Status command
    subparsers.add_parser('status', help='Show system status')
    
    # Daemon management commands
    start_parser = subparsers.add_parser('start', help='Start daemon')
    start_parser.add_argument('--foreground', action='store_true', help='Run in foreground')
    
    subparsers.add_parser('stop', help='Stop daemon')
    subparsers.add_parser('restart', help='Restart daemon')
    
    # Snapshot management commands
    snapshot_parser = subparsers.add_parser('snapshots', help='Manage snapshots')
    snapshot_parser.add_argument(
        'snapshot_action',
        choices=['list', 'create', 'delete', 'restore'],
        help='Snapshot action to perform'
    )
    snapshot_parser.add_argument('--snapshot-id', help='Snapshot ID for delete/restore operations')
    snapshot_parser.add_argument('--description', help='Description for new snapshot')
    
    # Timeout management commands
    subparsers.add_parser('timeouts', help='List active timeouts')
    
    confirm_parser = subparsers.add_parser('confirm', help='Confirm a configuration change')
    confirm_parser.add_argument('change_id', help='Change ID to confirm')
    
    # Test command
    subparsers.add_parser('test', help='Test system compatibility')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    cli = MeshAdminCLI()
    cli.config_path = args.config
    cli.setup_logging(args.verbose)
    
    # Route to appropriate command handler
    command_handlers = {
        'status': cli.cmd_status,
        'start': cli.cmd_start,
        'stop': cli.cmd_stop,
        'restart': cli.cmd_restart,
        'snapshots': cli.cmd_snapshots,
        'timeouts': cli.cmd_timeouts,
        'confirm': cli.cmd_confirm,
        'test': cli.cmd_test
    }
    
    handler = command_handlers.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"Unknown command: {args.command}")
        return 1


if __name__ == '__main__':
    sys.exit(main())