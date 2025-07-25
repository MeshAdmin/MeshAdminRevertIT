#!/usr/bin/env python3
"""
Tests for SnapshotManager functionality.
"""

import unittest
from unittest.mock import MagicMock, patch, mock_open
import tempfile
import shutil
import os
import json
from pathlib import Path

from meshadmin_revertit.snapshot.manager import SnapshotManager


class TestSnapshotManager(unittest.TestCase):
    """Test cases for SnapshotManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = {
            'enable_timeshift': False,  # Disable for testing
            'snapshot_location': os.path.join(self.temp_dir, 'snapshots'),
            'max_snapshots': 5,
            'compress_snapshots': False  # Disable for easier testing
        }
        
        self.distro_info = {
            'id': 'ubuntu',
            'name': 'Ubuntu',
            'family': 'debian'
        }
        
        self.snapshot_manager = SnapshotManager(self.config, self.distro_info)
    
    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_init(self):
        """Test SnapshotManager initialization."""
        self.assertEqual(self.snapshot_manager.config, self.config)
        self.assertEqual(self.snapshot_manager.distro_info, self.distro_info)
        self.assertFalse(self.snapshot_manager.timeshift_available)
        self.assertEqual(self.snapshot_manager.max_snapshots, 5)
        self.assertFalse(self.snapshot_manager.compress_snapshots)
        
        # Check that snapshot directory was created
        self.assertTrue(os.path.exists(self.config['snapshot_location']))
    
    @patch('subprocess.run')
    def test_check_timeshift_availability_found(self, mock_run):
        """Test TimeShift availability detection when available."""
        # Mock successful 'which timeshift' and 'timeshift --list'
        mock_results = [
            MagicMock(returncode=0),  # which timeshift
            MagicMock(returncode=0)   # timeshift --list
        ]
        mock_run.side_effect = mock_results
        
        result = self.snapshot_manager._check_timeshift_availability()
        self.assertTrue(result)
    
    @patch('subprocess.run')
    def test_check_timeshift_availability_not_found(self, mock_run):
        """Test TimeShift availability detection when not available."""
        # Mock failed 'which timeshift'
        mock_run.return_value = MagicMock(returncode=1)
        
        result = self.snapshot_manager._check_timeshift_availability()
        self.assertFalse(result)
    
    def test_create_manual_snapshot(self):
        """Test creating a manual snapshot."""
        # Create some test files to snapshot
        test_file = os.path.join(self.temp_dir, 'test_config')
        with open(test_file, 'w') as f:
            f.write('test configuration')
        
        # Mock os.path.exists to return True for our test file
        with patch('os.path.exists') as mock_exists:
            def exists_side_effect(path):
                return path == test_file
            mock_exists.side_effect = exists_side_effect
            
            # Mock the critical files list to include our test file
            with patch.object(self.snapshot_manager, '_create_manual_snapshot') as mock_create:
                mock_create.return_value = 'test_snapshot_123'
                
                snapshot_id = self.snapshot_manager.create_snapshot('Test snapshot')
                
                self.assertEqual(snapshot_id, 'test_snapshot_123')
                mock_create.assert_called_once()
    
    def test_backup_path_file(self):
        """Test backing up a single file."""
        # Create test file
        test_file = os.path.join(self.temp_dir, 'test.conf')
        with open(test_file, 'w') as f:
            f.write('test content')
        
        # Create snapshot directory
        snapshot_dir = Path(os.path.join(self.temp_dir, 'test_snapshot'))
        snapshot_dir.mkdir(parents=True)
        
        metadata = {'files': []}
        
        # Backup the file
        self.snapshot_manager._backup_path(test_file, snapshot_dir, metadata)
        
        # Check that file was backed up
        backed_up_file = snapshot_dir / Path(test_file).relative_to('/')
        self.assertTrue(backed_up_file.exists())
        
        # Check metadata was updated
        self.assertEqual(len(metadata['files']), 1)
        self.assertEqual(metadata['files'][0]['path'], test_file)
        self.assertEqual(metadata['files'][0]['type'], 'file')
    
    def test_backup_path_directory(self):
        """Test backing up a directory."""
        # Create test directory with files
        test_dir = os.path.join(self.temp_dir, 'test_dir')
        os.makedirs(test_dir)
        with open(os.path.join(test_dir, 'file1.conf'), 'w') as f:
            f.write('file1 content')
        with open(os.path.join(test_dir, 'file2.conf'), 'w') as f:
            f.write('file2 content')
        
        # Create snapshot directory
        snapshot_dir = Path(os.path.join(self.temp_dir, 'test_snapshot'))
        snapshot_dir.mkdir(parents=True)
        
        metadata = {'files': []}
        
        # Backup the directory
        self.snapshot_manager._backup_path(test_dir, snapshot_dir, metadata)
        
        # Check that directory was backed up
        backed_up_dir = snapshot_dir / Path(test_dir).relative_to('/')
        self.assertTrue(backed_up_dir.exists())
        self.assertTrue((backed_up_dir / 'file1.conf').exists())
        self.assertTrue((backed_up_dir / 'file2.conf').exists())
        
        # Check metadata was updated
        self.assertEqual(len(metadata['files']), 1)
        self.assertEqual(metadata['files'][0]['path'], test_dir)
        self.assertEqual(metadata['files'][0]['type'], 'directory')
    
    def test_list_manual_snapshots(self):
        """Test listing manual snapshots."""
        # Create some test snapshots
        snapshot_ids = ['test_snapshot_1', 'test_snapshot_2']
        
        for snapshot_id in snapshot_ids:
            snapshot_dir = Path(self.config['snapshot_location']) / snapshot_id
            snapshot_dir.mkdir(parents=True)
            
            # Create metadata file
            metadata = {
                'id': snapshot_id,
                'description': f'Test snapshot {snapshot_id}',
                'timestamp': '2023-01-01T12:00:00',
                'type': 'manual',
                'files': []
            }
            
            with open(snapshot_dir / 'metadata.json', 'w') as f:
                json.dump(metadata, f)
        
        # List snapshots
        snapshots = self.snapshot_manager._list_manual_snapshots()
        
        self.assertEqual(len(snapshots), 2)
        
        # Check snapshot details
        snapshot_ids_found = [s['id'] for s in snapshots]
        self.assertIn('test_snapshot_1', snapshot_ids_found)
        self.assertIn('test_snapshot_2', snapshot_ids_found)
    
    def test_delete_manual_snapshot(self):
        """Test deleting a manual snapshot."""
        # Create test snapshot
        snapshot_id = 'test_snapshot_delete'
        snapshot_dir = Path(self.config['snapshot_location']) / snapshot_id
        snapshot_dir.mkdir(parents=True)
        
        # Create some files in the snapshot
        (snapshot_dir / 'test_file').write_text('test content')
        
        # Delete the snapshot
        success = self.snapshot_manager._delete_manual_snapshot(snapshot_id)
        
        self.assertTrue(success)
        self.assertFalse(snapshot_dir.exists())
    
    def test_delete_nonexistent_snapshot(self):
        """Test deleting a nonexistent snapshot."""
        success = self.snapshot_manager._delete_manual_snapshot('nonexistent_snapshot')
        self.assertFalse(success)
    
    def test_restore_file(self):
        """Test restoring a single file from snapshot."""
        # Create original file
        original_file = os.path.join(self.temp_dir, 'original.conf')
        with open(original_file, 'w') as f:
            f.write('original content')
        
        # Create snapshot directory with backed up file
        snapshot_dir = Path(self.config['snapshot_location']) / 'test_snapshot'
        snapshot_dir.mkdir(parents=True)
        
        backed_up_file = snapshot_dir / Path(original_file).relative_to('/')
        backed_up_file.parent.mkdir(parents=True, exist_ok=True)
        backed_up_file.write_text('backed up content')
        
        # Modify original file
        with open(original_file, 'w') as f:
            f.write('modified content')
        
        # Restore file
        file_info = {
            'path': original_file,
            'type': 'file',
            'mode': '0o644'
        }
        
        self.snapshot_manager._restore_file(file_info, snapshot_dir)
        
        # Check that file was restored
        with open(original_file, 'r') as f:
            content = f.read()
        
        self.assertEqual(content, 'backed up content')
    
    def test_cleanup_old_snapshots(self):
        """Test cleanup of old snapshots."""
        # Create more snapshots than the maximum
        snapshot_ids = [f'test_snapshot_{i}' for i in range(7)]  # Max is 5
        
        for i, snapshot_id in enumerate(snapshot_ids):
            snapshot_dir = Path(self.config['snapshot_location']) / snapshot_id
            snapshot_dir.mkdir(parents=True)
            
            # Create metadata with different timestamps
            metadata = {
                'id': snapshot_id,
                'timestamp': f'2023-01-{i+1:02d}T12:00:00',
                'type': 'manual'
            }
            
            with open(snapshot_dir / 'metadata.json', 'w') as f:
                json.dump(metadata, f)
        
        # Run cleanup
        self.snapshot_manager.cleanup_old_snapshots()
        
        # Should only have 5 snapshots remaining (the newest ones)
        remaining_snapshots = self.snapshot_manager._list_manual_snapshots()
        self.assertEqual(len(remaining_snapshots), 5)
        
        # Check that the oldest snapshots were deleted
        remaining_ids = [s['id'] for s in remaining_snapshots]
        self.assertNotIn('test_snapshot_0', remaining_ids)  # Oldest
        self.assertNotIn('test_snapshot_1', remaining_ids)  # Second oldest
        self.assertIn('test_snapshot_6', remaining_ids)     # Newest
    
    @patch('subprocess.run')
    def test_compress_snapshot(self, mock_run):
        """Test snapshot compression."""
        # Create test snapshot directory
        snapshot_dir = Path(self.config['snapshot_location']) / 'test_snapshot'
        snapshot_dir.mkdir(parents=True)
        (snapshot_dir / 'test_file').write_text('test content')
        
        # Enable compression for this test
        self.snapshot_manager.compress_snapshots = True
        
        # Mock successful tar command
        mock_run.return_value = MagicMock(returncode=0)
        
        # Compress the snapshot
        self.snapshot_manager._compress_snapshot(snapshot_dir)
        
        # Check that tar was called correctly
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], 'tar')
        self.assertIn('-czf', call_args)
    
    def test_get_snapshot_info(self):
        """Test getting information about a specific snapshot."""
        # Create test snapshot
        snapshot_id = 'test_snapshot_info'
        snapshot_dir = Path(self.config['snapshot_location']) / snapshot_id
        snapshot_dir.mkdir(parents=True)
        
        metadata = {
            'id': snapshot_id,
            'description': 'Test snapshot for info',
            'timestamp': '2023-01-01T12:00:00',
            'type': 'manual',
            'files': []
        }
        
        with open(snapshot_dir / 'metadata.json', 'w') as f:
            json.dump(metadata, f)
        
        # Get snapshot info
        info = self.snapshot_manager.get_snapshot_info(snapshot_id)
        
        self.assertIsNotNone(info)
        self.assertEqual(info['id'], snapshot_id)
        self.assertEqual(info['description'], 'Test snapshot for info')
    
    def test_get_nonexistent_snapshot_info(self):
        """Test getting info for nonexistent snapshot."""
        info = self.snapshot_manager.get_snapshot_info('nonexistent')
        self.assertIsNone(info)


if __name__ == '__main__':
    unittest.main()