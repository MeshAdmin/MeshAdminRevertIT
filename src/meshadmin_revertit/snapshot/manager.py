#!/usr/bin/env python3
"""
Snapshot Manager - Handles system snapshots using TimeShift integration.
"""

import os
import subprocess
import logging
import json
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


class SnapshotManager:
    """Manages system snapshots for configuration reversion."""
    
    def __init__(self, config: Dict[str, Any], distro_info: Dict[str, str]):
        """Initialize snapshot manager with configuration."""
        self.config = config
        self.distro_info = distro_info
        self.logger = logging.getLogger(__name__)
        
        self.timeshift_available = self._check_timeshift_availability()
        self.snapshot_location = Path(config.get('snapshot_location', '/var/lib/meshadmin-revertit/snapshots'))
        self.max_snapshots = config.get('max_snapshots', 10)
        self.compress_snapshots = config.get('compress_snapshots', True)
        
        # Ensure snapshot directory exists
        self.snapshot_location.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Snapshot manager initialized. TimeShift available: {self.timeshift_available}")
    
    def _check_timeshift_availability(self) -> bool:
        """Check if TimeShift is available on the system."""
        try:
            result = subprocess.run(['which', 'timeshift'], 
                                  capture_output=True, text=True, check=False)
            available = result.returncode == 0
            
            if available:
                # Check if TimeShift is properly configured
                result = subprocess.run(['timeshift', '--list'], 
                                      capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    self.logger.warning("TimeShift found but not properly configured")
                    return False
            
            return available
        except Exception as e:
            self.logger.error(f"Error checking TimeShift availability: {e}")
            return False
    
    def create_snapshot(self, description: str = None) -> str:
        """Create a new system snapshot."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_id = f"meshadmin_revertit_{timestamp}"
        
        if description is None:
            description = f"MeshAdminRevertIt snapshot created at {datetime.now().isoformat()}"
        
        self.logger.info(f"Creating snapshot: {snapshot_id}")
        
        if self.timeshift_available and self.config.get('enable_timeshift', True):
            return self._create_timeshift_snapshot(snapshot_id, description)
        else:
            return self._create_manual_snapshot(snapshot_id, description)
    
    def _create_timeshift_snapshot(self, snapshot_id: str, description: str) -> str:
        """Create snapshot using TimeShift."""
        try:
            cmd = [
                'timeshift', 
                '--create', 
                '--comments', description,
                '--tags', 'D'  # Daily tag
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            
            # Parse TimeShift output to get actual snapshot name
            actual_snapshot_id = self._parse_timeshift_snapshot_id(result.stdout)
            
            self.logger.info(f"TimeShift snapshot created: {actual_snapshot_id}")
            return actual_snapshot_id
            
        except subprocess.CalledProcessError as e:
            self.logger.error(f"TimeShift snapshot creation failed: {e.stderr}")
            # Fallback to manual snapshot
            return self._create_manual_snapshot(snapshot_id, description)
    
    def _parse_timeshift_snapshot_id(self, timeshift_output: str) -> str:
        """Parse TimeShift output to extract snapshot ID."""
        # TimeShift typically outputs the snapshot name in its output
        lines = timeshift_output.split('\n')
        for line in lines:
            if 'Snapshot saved successfully' in line or 'created in' in line:
                # Extract snapshot ID from the line
                # This is a simplified parser - may need adjustment based on TimeShift version
                parts = line.split()
                for part in parts:
                    if part.startswith('20') and '_' in part:  # Looks like a timestamp
                        return part
        
        # Fallback: generate our own ID
        return f"meshadmin_revertit_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def _create_manual_snapshot(self, snapshot_id: str, description: str) -> str:
        """Create manual snapshot of critical configuration files."""
        snapshot_dir = self.snapshot_location / snapshot_id
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        # Create snapshot metadata
        metadata = {
            'id': snapshot_id,
            'description': description,
            'timestamp': datetime.now().isoformat(),
            'type': 'manual',
            'files': []
        }
        
        # Critical files to backup
        critical_files = [
            '/etc/network/interfaces',
            '/etc/netplan',
            '/etc/NetworkManager/system-connections',
            '/etc/systemd/network',
            '/etc/ssh/sshd_config',
            '/etc/ssh/ssh_config.d',
            '/etc/iptables',
            '/etc/ufw',
            '/etc/firewalld',
            '/etc/systemd/system',
            '/etc/hosts',
            '/etc/resolv.conf',
            '/etc/hostname'
        ]
        
        for file_path in critical_files:
            if os.path.exists(file_path):
                try:
                    self._backup_path(file_path, snapshot_dir, metadata)
                except Exception as e:
                    self.logger.warning(f"Failed to backup {file_path}: {e}")
        
        # Save metadata
        metadata_file = snapshot_dir / 'metadata.json'
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)
        
        # Compress if enabled
        if self.compress_snapshots:
            self._compress_snapshot(snapshot_dir)
        
        self.logger.info(f"Manual snapshot created: {snapshot_id}")
        return snapshot_id
    
    def _backup_path(self, source_path: str, snapshot_dir: Path, metadata: Dict) -> None:
        """Backup a file or directory to the snapshot."""
        source = Path(source_path)
        
        if not source.exists():
            return
        
        # Create relative path structure in snapshot
        if source.is_absolute():
            relative_path = source.relative_to('/')
        else:
            relative_path = source
        
        target = snapshot_dir / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        
        if source.is_file():
            shutil.copy2(source, target)
            metadata['files'].append({
                'path': str(source),
                'type': 'file',
                'size': source.stat().st_size,
                'mode': oct(source.stat().st_mode)
            })
        elif source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
            metadata['files'].append({
                'path': str(source),
                'type': 'directory',
                'mode': oct(source.stat().st_mode)
            })
    
    def _compress_snapshot(self, snapshot_dir: Path) -> None:
        """Compress snapshot directory."""
        try:
            archive_path = f"{snapshot_dir}.tar.gz"
            subprocess.run([
                'tar', '-czf', archive_path, 
                '-C', str(snapshot_dir.parent), 
                snapshot_dir.name
            ], check=True)
            
            # Remove uncompressed directory
            shutil.rmtree(snapshot_dir)
            
            self.logger.debug(f"Snapshot compressed: {archive_path}")
        except Exception as e:
            self.logger.warning(f"Failed to compress snapshot {snapshot_dir}: {e}")
    
    def list_snapshots(self) -> List[Dict[str, Any]]:
        """List all available snapshots."""
        snapshots = []
        
        if self.timeshift_available and self.config.get('enable_timeshift', True):
            snapshots.extend(self._list_timeshift_snapshots())
        
        snapshots.extend(self._list_manual_snapshots())
        
        # Sort by timestamp (newest first)
        snapshots.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return snapshots
    
    def _list_timeshift_snapshots(self) -> List[Dict[str, Any]]:
        """List TimeShift snapshots."""
        snapshots = []
        
        try:
            result = subprocess.run(['timeshift', '--list'], 
                                  capture_output=True, text=True, check=True)
            
            # Parse TimeShift output
            lines = result.stdout.split('\n')
            in_snapshot_list = False
            
            for line in lines:
                line = line.strip()
                if 'Num     Name' in line:
                    in_snapshot_list = True
                    continue
                
                if in_snapshot_list and line and not line.startswith('--'):
                    parts = line.split()
                    if len(parts) >= 3:
                        snapshots.append({
                            'id': parts[1],
                            'type': 'timeshift',
                            'timestamp': parts[1],  # TimeShift uses timestamp as name
                            'description': ' '.join(parts[2:]) if len(parts) > 2 else ''
                        })
        
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Failed to list TimeShift snapshots: {e.stderr}")
        
        return snapshots
    
    def _list_manual_snapshots(self) -> List[Dict[str, Any]]:
        """List manual snapshots."""
        snapshots = []
        
        if not self.snapshot_location.exists():
            return snapshots
        
        for item in self.snapshot_location.iterdir():
            if item.is_dir() or item.name.endswith('.tar.gz'):
                snapshot_id = item.name.replace('.tar.gz', '')
                
                # Try to load metadata
                metadata_file = None
                if item.is_dir():
                    metadata_file = item / 'metadata.json'
                else:
                    # For compressed snapshots, we'd need to extract metadata
                    # For now, use basic info
                    pass
                
                snapshot_info = {
                    'id': snapshot_id,
                    'type': 'manual',
                    'timestamp': snapshot_id.replace('meshadmin_revertit_', ''),
                    'description': 'Manual snapshot'
                }
                
                if metadata_file and metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                            snapshot_info.update(metadata)
                    except Exception as e:
                        self.logger.warning(f"Failed to load metadata for {snapshot_id}: {e}")
                
                snapshots.append(snapshot_info)
        
        return snapshots
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a specific snapshot."""
        self.logger.info(f"Deleting snapshot: {snapshot_id}")
        
        # Try TimeShift first
        if self.timeshift_available:
            if self._delete_timeshift_snapshot(snapshot_id):
                return True
        
        # Try manual snapshot
        return self._delete_manual_snapshot(snapshot_id)
    
    def _delete_timeshift_snapshot(self, snapshot_id: str) -> bool:
        """Delete TimeShift snapshot."""
        try:
            result = subprocess.run(['timeshift', '--delete', '--snapshot', snapshot_id], 
                                  capture_output=True, text=True, check=True)
            self.logger.info(f"TimeShift snapshot deleted: {snapshot_id}")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.debug(f"Failed to delete TimeShift snapshot {snapshot_id}: {e.stderr}")
            return False
    
    def _delete_manual_snapshot(self, snapshot_id: str) -> bool:
        """Delete manual snapshot."""
        snapshot_dir = self.snapshot_location / snapshot_id
        snapshot_archive = self.snapshot_location / f"{snapshot_id}.tar.gz"
        
        try:
            if snapshot_dir.exists():
                shutil.rmtree(snapshot_dir)
                self.logger.info(f"Manual snapshot directory deleted: {snapshot_id}")
                return True
            elif snapshot_archive.exists():
                snapshot_archive.unlink()
                self.logger.info(f"Manual snapshot archive deleted: {snapshot_id}")
                return True
        except Exception as e:
            self.logger.error(f"Failed to delete manual snapshot {snapshot_id}: {e}")
        
        return False
    
    def cleanup_old_snapshots(self) -> None:
        """Clean up old snapshots beyond the maximum limit."""
        snapshots = self.list_snapshots()
        
        if len(snapshots) <= self.max_snapshots:
            return
        
        # Delete oldest snapshots
        snapshots_to_delete = snapshots[self.max_snapshots:]
        
        for snapshot in snapshots_to_delete:
            self.delete_snapshot(snapshot['id'])
        
        self.logger.info(f"Cleaned up {len(snapshots_to_delete)} old snapshots")
    
    def restore_snapshot(self, snapshot_id: str) -> bool:
        """Restore system from a snapshot."""
        self.logger.info(f"Restoring from snapshot: {snapshot_id}")
        
        snapshots = self.list_snapshots()
        snapshot = next((s for s in snapshots if s['id'] == snapshot_id), None)
        
        if not snapshot:
            self.logger.error(f"Snapshot not found: {snapshot_id}")
            return False
        
        if snapshot['type'] == 'timeshift':
            return self._restore_timeshift_snapshot(snapshot_id)
        else:
            return self._restore_manual_snapshot(snapshot_id)
    
    def _restore_timeshift_snapshot(self, snapshot_id: str) -> bool:
        """Restore from TimeShift snapshot."""
        try:
            result = subprocess.run(['timeshift', '--restore', '--snapshot', snapshot_id], 
                                  capture_output=True, text=True, check=True)
            self.logger.info(f"TimeShift restoration completed: {snapshot_id}")
            return True
        except subprocess.CalledProcessError as e:
            self.logger.error(f"TimeShift restoration failed: {e.stderr}")
            return False
    
    def _restore_manual_snapshot(self, snapshot_id: str) -> bool:
        """Restore from manual snapshot."""
        snapshot_dir = self.snapshot_location / snapshot_id
        snapshot_archive = self.snapshot_location / f"{snapshot_id}.tar.gz"
        
        # Extract if compressed
        if snapshot_archive.exists() and not snapshot_dir.exists():
            try:
                subprocess.run([
                    'tar', '-xzf', str(snapshot_archive), 
                    '-C', str(self.snapshot_location)
                ], check=True)
            except subprocess.CalledProcessError as e:
                self.logger.error(f"Failed to extract snapshot {snapshot_id}: {e}")
                return False
        
        if not snapshot_dir.exists():
            self.logger.error(f"Snapshot directory not found: {snapshot_dir}")
            return False
        
        # Load metadata
        metadata_file = snapshot_dir / 'metadata.json'
        if not metadata_file.exists():
            self.logger.error(f"Snapshot metadata not found: {metadata_file}")
            return False
        
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load snapshot metadata: {e}")
            return False
        
        # Restore files
        success = True
        for file_info in metadata.get('files', []):
            try:
                self._restore_file(file_info, snapshot_dir)
            except Exception as e:
                self.logger.error(f"Failed to restore {file_info['path']}: {e}")
                success = False
        
        self.logger.info(f"Manual snapshot restoration completed: {snapshot_id}")
        return success
    
    def _restore_file(self, file_info: Dict[str, Any], snapshot_dir: Path) -> None:
        """Restore individual file from snapshot."""
        source_path = file_info['path']
        target_path = Path(source_path)
        
        # Calculate source path in snapshot
        if target_path.is_absolute():
            relative_path = target_path.relative_to('/')
        else:
            relative_path = target_path
        
        source_file = snapshot_dir / relative_path
        
        if not source_file.exists():
            self.logger.warning(f"Source file not found in snapshot: {source_file}")
            return
        
        # Create target directory if needed
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Restore file or directory
        if file_info['type'] == 'file':
            shutil.copy2(source_file, target_path)
        elif file_info['type'] == 'directory':
            if target_path.exists():
                shutil.rmtree(target_path)
            shutil.copytree(source_file, target_path)
        
        # Restore permissions
        try:
            mode = int(file_info['mode'], 8)
            os.chmod(target_path, mode)
        except Exception as e:
            self.logger.warning(f"Failed to restore permissions for {target_path}: {e}")
    
    def get_snapshot_info(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific snapshot."""
        snapshots = self.list_snapshots()
        return next((s for s in snapshots if s['id'] == snapshot_id), None)