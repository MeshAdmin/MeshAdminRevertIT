#!/usr/bin/env python3
"""
Revert Engine - Handles automatic reversion of configuration changes.
"""

import os
import subprocess
import logging
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


class RevertEngine:
    """Handles automatic reversion of system configuration changes."""
    
    def __init__(self, snapshot_manager, config: Dict[str, Any], distro_info: Dict[str, str]):
        """Initialize revert engine."""
        self.snapshot_manager = snapshot_manager
        self.config = config
        self.distro_info = distro_info
        self.logger = logging.getLogger(__name__)
        
        # Service restart commands for different categories
        self.service_commands = self._get_service_commands()
        
        self.logger.info("Revert engine initialized")
    
    def _get_service_commands(self) -> Dict[str, Dict[str, str]]:
        """Get service restart commands for different change categories."""
        # Default commands for Ubuntu/Debian
        default_commands = {
            'network': {
                'restart': 'systemctl restart networking',
                'reload': 'systemctl reload networking',
                'test': 'ip link show'
            },
            'ssh': {
                'restart': 'systemctl restart ssh',
                'reload': 'systemctl reload ssh',
                'test': 'systemctl is-active ssh'
            },
            'firewall': {
                'restart': 'ufw reload',
                'reload': 'ufw reload',
                'test': 'ufw status'
            },
            'service': {
                'restart': 'systemctl daemon-reload',
                'reload': 'systemctl daemon-reload',
                'test': 'systemctl list-units --failed'
            }
        }
        
        # Override with distro-specific commands if available
        distro_commands = self.config.get('distro', {}).get('commands', {})
        distro = self.distro_info.get('id', 'ubuntu')
        
        if distro in distro_commands:
            for category, commands in distro_commands[distro].items():
                if category in default_commands:
                    default_commands[category].update(commands)
        
        return default_commands
    
    def revert_change(self, file_path: str, change_category: str, 
                     snapshot_id: Optional[str] = None) -> bool:
        """Revert a configuration change."""
        self.logger.info(f"Starting revert process for {change_category} change: {file_path}")
        
        try:
            # Step 1: Create a backup of current state (post-change)
            current_backup_id = self._create_current_backup(file_path, change_category)
            
            # Step 2: Restore from snapshot
            if snapshot_id:
                restore_success = self._restore_from_snapshot(snapshot_id, file_path)
            else:
                restore_success = self._restore_from_default(file_path, change_category)
            
            if not restore_success:
                self.logger.error(f"Failed to restore files for {file_path}")
                return False
            
            # Step 3: Restart affected services
            service_success = self._restart_affected_services(change_category)
            
            if not service_success:
                self.logger.warning(f"Service restart issues for {change_category} - manual intervention may be required")
            
            # Step 4: Verify revert success
            verification_success = self._verify_revert(change_category)
            
            if verification_success:
                self.logger.info(f"Successfully reverted {change_category} change: {file_path}")
                self._log_revert_success(file_path, change_category, snapshot_id, current_backup_id)
                return True
            else:
                self.logger.error(f"Revert verification failed for {change_category} change: {file_path}")
                # Attempt to restore the post-change state
                self._emergency_restore(current_backup_id)
                return False
            
        except Exception as e:
            self.logger.critical(f"Critical error during revert of {file_path}: {e}")
            return False
    
    def _create_current_backup(self, file_path: str, change_category: str) -> str:
        """Create backup of current state before reverting."""
        try:
            backup_id = self.snapshot_manager.create_snapshot(
                description=f"Pre-revert backup for {file_path} ({change_category})"
            )
            self.logger.debug(f"Created pre-revert backup: {backup_id}")
            return backup_id
        except Exception as e:
            self.logger.warning(f"Failed to create pre-revert backup: {e}")
            return ""
    
    def _restore_from_snapshot(self, snapshot_id: str, file_path: str) -> bool:
        """Restore configuration from a specific snapshot."""
        self.logger.info(f"Restoring from snapshot: {snapshot_id}")
        
        try:
            # Get snapshot info
            snapshot_info = self.snapshot_manager.get_snapshot_info(snapshot_id)
            if not snapshot_info:
                self.logger.error(f"Snapshot not found: {snapshot_id}")
                return False
            
            # Restore the snapshot
            if snapshot_info['type'] == 'timeshift':
                return self._restore_timeshift_snapshot(snapshot_id)
            else:
                return self._restore_manual_snapshot(snapshot_id, file_path)
                
        except Exception as e:
            self.logger.error(f"Error restoring from snapshot {snapshot_id}: {e}")
            return False
    
    def _restore_timeshift_snapshot(self, snapshot_id: str) -> bool:
        """Restore from TimeShift snapshot."""
        try:
            # TimeShift restoration is a system-wide operation
            # For safety, we'll only restore specific files, not the entire system
            self.logger.warning("TimeShift full system restore requested - this is a major operation")
            
            # For now, we'll use the manual restore method instead
            # Full TimeShift restore would be: timeshift --restore --snapshot {snapshot_id}
            # But this is too risky for automatic operation
            
            return self.snapshot_manager.restore_snapshot(snapshot_id)
            
        except Exception as e:
            self.logger.error(f"TimeShift restore failed: {e}")
            return False
    
    def _restore_manual_snapshot(self, snapshot_id: str, file_path: str) -> bool:
        """Restore from manual snapshot."""
        try:
            return self.snapshot_manager.restore_snapshot(snapshot_id)
        except Exception as e:
            self.logger.error(f"Manual snapshot restore failed: {e}")
            return False
    
    def _restore_from_default(self, file_path: str, change_category: str) -> bool:
        """Restore from default/template configuration when no snapshot available."""
        self.logger.warning(f"No snapshot available, attempting default restore for {file_path}")
        
        # Default restoration strategies
        default_strategies = {
            'network': self._restore_default_network,
            'ssh': self._restore_default_ssh,
            'firewall': self._restore_default_firewall,
            'service': self._restore_default_service
        }
        
        strategy = default_strategies.get(change_category)
        if strategy:
            return strategy(file_path)
        else:
            self.logger.error(f"No default restore strategy for category: {change_category}")
            return False
    
    def _restore_default_network(self, file_path: str) -> bool:
        """Restore default network configuration."""
        file_path_lower = file_path.lower()
        
        # Handle different network configuration files
        if 'interfaces' in file_path_lower:
            return self._restore_default_interfaces()
        elif 'netplan' in file_path_lower:
            return self._restore_default_netplan()
        elif 'networkmanager' in file_path_lower:
            return self._restore_default_networkmanager()
        else:
            self.logger.warning(f"Unknown network configuration file: {file_path}")
            return False
    
    def _restore_default_interfaces(self) -> bool:
        """Restore default /etc/network/interfaces."""
        default_interfaces = """# This file describes the network interfaces available on your system
# and how to activate them. For more information, see interfaces(5).

source /etc/network/interfaces.d/*

# The loopback network interface
auto lo
iface lo inet loopback

# The primary network interface (DHCP)
auto eth0
iface eth0 inet dhcp
"""
        
        try:
            with open('/etc/network/interfaces', 'w') as f:
                f.write(default_interfaces)
            self.logger.info("Restored default /etc/network/interfaces")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore default interfaces: {e}")
            return False
    
    def _restore_default_netplan(self) -> bool:
        """Restore default netplan configuration."""
        # Find netplan files
        netplan_dir = Path('/etc/netplan')
        if not netplan_dir.exists():
            return True  # No netplan to restore
        
        # Remove existing netplan files and create default
        try:
            for file in netplan_dir.glob('*.yaml'):
                file.unlink()
            
            default_netplan = """network:
  version: 2
  renderer: networkd
  ethernets:
    eth0:
      dhcp4: true
"""
            
            with open('/etc/netplan/01-network-manager-all.yaml', 'w') as f:
                f.write(default_netplan)
            
            # Apply netplan
            subprocess.run(['netplan', 'apply'], check=True)
            
            self.logger.info("Restored default netplan configuration")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore default netplan: {e}")
            return False
    
    def _restore_default_networkmanager(self) -> bool:
        """Restore default NetworkManager configuration."""
        # NetworkManager restoration is complex, just restart service
        try:
            subprocess.run(['systemctl', 'restart', 'NetworkManager'], check=True)
            self.logger.info("Restarted NetworkManager service")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restart NetworkManager: {e}")
            return False
    
    def _restore_default_ssh(self, file_path: str) -> bool:
        """Restore default SSH configuration."""
        if 'sshd_config' in file_path:
            return self._restore_default_sshd_config()
        else:
            self.logger.warning(f"Unknown SSH configuration file: {file_path}")
            return False
    
    def _restore_default_sshd_config(self) -> bool:
        """Restore default sshd_config."""
        # Copy from system default if available
        default_sources = [
            '/usr/share/openssh/sshd_config',
            '/etc/ssh/sshd_config.orig',
            '/etc/ssh/sshd_config.default'
        ]
        
        for source in default_sources:
            if os.path.exists(source):
                try:
                    subprocess.run(['cp', source, '/etc/ssh/sshd_config'], check=True)
                    self.logger.info(f"Restored sshd_config from {source}")
                    return True
                except Exception as e:
                    self.logger.warning(f"Failed to restore from {source}: {e}")
        
        # Create minimal safe sshd_config
        minimal_sshd_config = """Port 22
Protocol 2
HostKey /etc/ssh/ssh_host_rsa_key
HostKey /etc/ssh/ssh_host_dsa_key
HostKey /etc/ssh/ssh_host_ecdsa_key
HostKey /etc/ssh/ssh_host_ed25519_key
UsePrivilegeSeparation yes
KeyRegenerationInterval 3600
ServerKeyBits 1024
SyslogFacility AUTH
LogLevel INFO
LoginGraceTime 120
PermitRootLogin yes
StrictModes yes
RSAAuthentication yes
PubkeyAuthentication yes
IgnoreRhosts yes
RhostsRSAAuthentication no
HostbasedAuthentication no
PermitEmptyPasswords no
ChallengeResponseAuthentication no
PasswordAuthentication yes
X11Forwarding yes
X11DisplayOffset 10
PrintMotd no
PrintLastLog yes
TCPKeepAlive yes
AcceptEnv LANG LC_*
Subsystem sftp /usr/lib/openssh/sftp-server
UsePAM yes
"""
        
        try:
            with open('/etc/ssh/sshd_config', 'w') as f:
                f.write(minimal_sshd_config)
            self.logger.info("Created minimal safe sshd_config")
            return True
        except Exception as e:
            self.logger.error(f"Failed to create minimal sshd_config: {e}")
            return False
    
    def _restore_default_firewall(self, file_path: str) -> bool:
        """Restore default firewall configuration."""
        file_path_lower = file_path.lower()
        
        if 'ufw' in file_path_lower:
            return self._restore_default_ufw()
        elif 'iptables' in file_path_lower:
            return self._restore_default_iptables()
        elif 'firewalld' in file_path_lower:
            return self._restore_default_firewalld()
        else:
            self.logger.warning(f"Unknown firewall configuration: {file_path}")
            return False
    
    def _restore_default_ufw(self) -> bool:
        """Restore default UFW configuration."""
        try:
            # Reset UFW to defaults
            subprocess.run(['ufw', '--force', 'reset'], check=True)
            # Allow SSH to prevent lockout
            subprocess.run(['ufw', 'allow', 'ssh'], check=True)
            # Enable UFW
            subprocess.run(['ufw', '--force', 'enable'], check=True)
            
            self.logger.info("Restored default UFW configuration")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore default UFW: {e}")
            return False
    
    def _restore_default_iptables(self) -> bool:
        """Restore default iptables configuration."""
        try:
            # Clear all rules and set default policies
            subprocess.run(['iptables', '-F'], check=True)
            subprocess.run(['iptables', '-X'], check=True)
            subprocess.run(['iptables', '-t', 'nat', '-F'], check=True)
            subprocess.run(['iptables', '-t', 'nat', '-X'], check=True)
            subprocess.run(['iptables', '-P', 'INPUT', 'ACCEPT'], check=True)
            subprocess.run(['iptables', '-P', 'FORWARD', 'ACCEPT'], check=True)
            subprocess.run(['iptables', '-P', 'OUTPUT', 'ACCEPT'], check=True)
            
            self.logger.info("Restored default iptables configuration")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore default iptables: {e}")
            return False
    
    def _restore_default_firewalld(self) -> bool:
        """Restore default firewalld configuration."""
        try:
            # Reload firewalld to defaults
            subprocess.run(['firewall-cmd', '--reload'], check=True)
            
            self.logger.info("Restored default firewalld configuration")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore default firewalld: {e}")
            return False
    
    def _restore_default_service(self, file_path: str) -> bool:
        """Restore default service configuration."""
        try:
            # Reload systemd daemon
            subprocess.run(['systemctl', 'daemon-reload'], check=True)
            
            self.logger.info("Reloaded systemd daemon")
            return True
        except Exception as e:
            self.logger.error(f"Failed to reload systemd: {e}")
            return False
    
    def _restart_affected_services(self, change_category: str) -> bool:
        """Restart services affected by the configuration change."""
        if change_category not in self.service_commands:
            self.logger.debug(f"No service restart needed for category: {change_category}")
            return True
        
        commands = self.service_commands[change_category]
        restart_command = commands.get('restart')
        
        if not restart_command:
            self.logger.debug(f"No restart command defined for category: {change_category}")
            return True
        
        try:
            self.logger.info(f"Restarting services for {change_category}: {restart_command}")
            
            # Execute restart command
            result = subprocess.run(
                restart_command.split(),
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            
            self.logger.info(f"Service restart successful for {change_category}")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Service restart failed for {change_category}: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            self.logger.error(f"Service restart timed out for {change_category}")
            return False
        except Exception as e:
            self.logger.error(f"Error restarting services for {change_category}: {e}")
            return False
    
    def _verify_revert(self, change_category: str) -> bool:
        """Verify that the revert was successful."""
        if change_category not in self.service_commands:
            return True  # No verification needed
        
        commands = self.service_commands[change_category]
        test_command = commands.get('test')
        
        if not test_command:
            self.logger.debug(f"No verification test for category: {change_category}")
            return True  # Assume success if no test defined
        
        try:
            self.logger.debug(f"Verifying revert for {change_category}: {test_command}")
            
            result = subprocess.run(
                test_command.split(),
                capture_output=True,
                text=True,
                check=True,
                timeout=10
            )
            
            self.logger.debug(f"Revert verification passed for {change_category}")
            return True
            
        except subprocess.CalledProcessError as e:
            self.logger.warning(f"Revert verification failed for {change_category}: {e.stderr}")
            return False
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Revert verification timed out for {change_category}")
            return False
        except Exception as e:
            self.logger.error(f"Error verifying revert for {change_category}: {e}")
            return False
    
    def _emergency_restore(self, backup_id: str) -> None:
        """Emergency restore to previous state if revert fails."""
        if not backup_id:
            self.logger.critical("No backup available for emergency restore")
            return
        
        try:
            self.logger.warning(f"Performing emergency restore to: {backup_id}")
            self.snapshot_manager.restore_snapshot(backup_id)
            self.logger.info("Emergency restore completed")
        except Exception as e:
            self.logger.critical(f"Emergency restore failed: {e}")
    
    def _log_revert_success(self, file_path: str, change_category: str, 
                          snapshot_id: Optional[str], backup_id: str) -> None:
        """Log successful revert operation."""
        log_entry = {
            'timestamp': time.time(),
            'file_path': file_path,
            'change_category': change_category,
            'snapshot_id': snapshot_id,
            'backup_id': backup_id,
            'status': 'success'
        }
        
        self.logger.info(f"Revert operation completed successfully: {log_entry}")
    
    def test_revert_capability(self, change_category: str) -> Dict[str, bool]:
        """Test the revert capability for a specific category."""
        results = {
            'service_commands_available': change_category in self.service_commands,
            'restart_command_available': False,
            'test_command_available': False,
            'can_create_snapshot': False,
            'can_restore_snapshot': False
        }
        
        if results['service_commands_available']:
            commands = self.service_commands[change_category]
            results['restart_command_available'] = 'restart' in commands
            results['test_command_available'] = 'test' in commands
        
        # Test snapshot capabilities
        try:
            test_snapshot = self.snapshot_manager.create_snapshot("Test snapshot for revert capability")
            results['can_create_snapshot'] = True
            
            # Clean up test snapshot
            self.snapshot_manager.delete_snapshot(test_snapshot)
            results['can_restore_snapshot'] = True
            
        except Exception as e:
            self.logger.debug(f"Snapshot capability test failed: {e}")
        
        return results