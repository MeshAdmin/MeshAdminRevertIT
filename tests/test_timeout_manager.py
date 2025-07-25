#!/usr/bin/env python3
"""
Tests for TimeoutManager functionality.
"""

import unittest
from unittest.mock import MagicMock, patch
import time
import threading
from datetime import datetime, timedelta

from meshadmin_revertit.timeout.manager import TimeoutManager, TimeoutEntry


class TestTimeoutEntry(unittest.TestCase):
    """Test cases for TimeoutEntry."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.start_time = datetime.now()
        self.entry = TimeoutEntry(
            change_id="test_123",
            file_path="/etc/test/config",
            change_category="test",
            snapshot_id="snap_123",
            event_type="modified",
            timeout_seconds=300,
            start_time=self.start_time
        )
    
    def test_init(self):
        """Test TimeoutEntry initialization."""
        self.assertEqual(self.entry.change_id, "test_123")
        self.assertEqual(self.entry.file_path, "/etc/test/config")
        self.assertEqual(self.entry.change_category, "test")
        self.assertEqual(self.entry.snapshot_id, "snap_123")
        self.assertEqual(self.entry.event_type, "modified")
        self.assertEqual(self.entry.timeout_seconds, 300)
        self.assertEqual(self.entry.start_time, self.start_time)
    
    def test_is_expired(self):
        """Test timeout expiry checking."""
        # Not expired yet
        current_time = self.start_time + timedelta(seconds=100)
        self.assertFalse(self.entry.is_expired(current_time))
        
        # Exactly at expiry
        current_time = self.start_time + timedelta(seconds=300)
        self.assertTrue(self.entry.is_expired(current_time))
        
        # Past expiry
        current_time = self.start_time + timedelta(seconds=400)
        self.assertTrue(self.entry.is_expired(current_time))
    
    def test_get_remaining_time(self):
        """Test remaining time calculation."""
        # Time remaining
        current_time = self.start_time + timedelta(seconds=100)
        remaining = self.entry.get_remaining_time(current_time)
        self.assertEqual(remaining.total_seconds(), 200)
        
        # No time remaining
        current_time = self.start_time + timedelta(seconds=400)
        remaining = self.entry.get_remaining_time(current_time)
        self.assertEqual(remaining.total_seconds(), 0)


class TestTimeoutManager(unittest.TestCase):
    """Test cases for TimeoutManager."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'timeout_action': 'revert',
            'connectivity_check': True,
            'connectivity_endpoints': ['8.8.8.8', '1.1.1.1'],
            'connectivity_timeout': 10,
            'revert_grace_period': 30
        }
        
        self.mock_revert_engine = MagicMock()
        self.timeout_manager = TimeoutManager(self.config, self.mock_revert_engine)
    
    def test_init(self):
        """Test TimeoutManager initialization."""
        self.assertEqual(self.timeout_manager.config, self.config)
        self.assertEqual(self.timeout_manager.revert_engine, self.mock_revert_engine)
        self.assertEqual(self.timeout_manager.connectivity_endpoints, ['8.8.8.8', '1.1.1.1'])
        self.assertEqual(self.timeout_manager.connectivity_timeout, 10)
        self.assertEqual(self.timeout_manager.grace_period, 30)
        self.assertFalse(self.timeout_manager.running)
        self.assertEqual(len(self.timeout_manager.active_timeouts), 0)
    
    def test_get_timeout_for_category(self):
        """Test timeout duration determination by category."""
        # Network change should get longer timeout
        timeout = self.timeout_manager._get_timeout_for_category('network')
        self.assertEqual(timeout, 600)
        
        # SSH change should get longest timeout
        timeout = self.timeout_manager._get_timeout_for_category('ssh')
        self.assertEqual(timeout, 900)
        
        # Default category
        timeout = self.timeout_manager._get_timeout_for_category('unknown')
        self.assertEqual(timeout, 300)
    
    def test_start_timeout(self):
        """Test starting a timeout."""
        success = self.timeout_manager.start_timeout(
            change_id="test_123",
            file_path="/etc/test/config",
            change_category="network",
            snapshot_id="snap_123"
        )
        
        self.assertTrue(success)
        self.assertIn("test_123", self.timeout_manager.active_timeouts)
        
        entry = self.timeout_manager.active_timeouts["test_123"]
        self.assertEqual(entry.file_path, "/etc/test/config")
        self.assertEqual(entry.change_category, "network")
        self.assertEqual(entry.timeout_seconds, 600)  # Network timeout
    
    def test_start_timeout_replaces_existing(self):
        """Test that starting a timeout for the same file replaces existing one."""
        # Start first timeout
        self.timeout_manager.start_timeout(
            change_id="test_123",
            file_path="/etc/test/config",
            change_category="network",
            snapshot_id="snap_123"
        )
        
        # Start second timeout for same file
        self.timeout_manager.start_timeout(
            change_id="test_456",
            file_path="/etc/test/config",
            change_category="ssh",
            snapshot_id="snap_456"
        )
        
        # Should only have the second timeout
        self.assertEqual(len(self.timeout_manager.active_timeouts), 1)
        self.assertNotIn("test_123", self.timeout_manager.active_timeouts)
        self.assertIn("test_456", self.timeout_manager.active_timeouts)
    
    def test_confirm_change(self):
        """Test confirming a configuration change."""
        # Start a timeout
        self.timeout_manager.start_timeout(
            change_id="test_123",
            file_path="/etc/test/config",
            change_category="network"
        )
        
        # Confirm the change
        success = self.timeout_manager.confirm_change("test_123")
        
        self.assertTrue(success)
        self.assertNotIn("test_123", self.timeout_manager.active_timeouts)
    
    def test_confirm_unknown_change(self):
        """Test confirming unknown change ID."""
        success = self.timeout_manager.confirm_change("unknown_123")
        self.assertFalse(success)
    
    def test_list_active_timeouts(self):
        """Test listing active timeouts."""
        # Start some timeouts
        self.timeout_manager.start_timeout(
            change_id="test_123",
            file_path="/etc/test/config1",
            change_category="network"
        )
        
        self.timeout_manager.start_timeout(
            change_id="test_456",
            file_path="/etc/test/config2",
            change_category="ssh"
        )
        
        timeouts = self.timeout_manager.list_active_timeouts()
        
        self.assertEqual(len(timeouts), 2)
        
        # Check first timeout
        timeout1 = next(t for t in timeouts if t['change_id'] == 'test_123')
        self.assertEqual(timeout1['file_path'], '/etc/test/config1')
        self.assertEqual(timeout1['change_category'], 'network')
        self.assertEqual(timeout1['timeout_seconds'], 600)
        
        # Check second timeout
        timeout2 = next(t for t in timeouts if t['change_id'] == 'test_456')
        self.assertEqual(timeout2['file_path'], '/etc/test/config2')
        self.assertEqual(timeout2['change_category'], 'ssh')
        self.assertEqual(timeout2['timeout_seconds'], 900)
    
    @patch('subprocess.run')
    @patch('socket.gethostbyname')
    def test_check_connectivity_success(self, mock_gethostbyname, mock_run):
        """Test successful connectivity check."""
        mock_gethostbyname.return_value = '8.8.8.8'
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        result = self.timeout_manager._check_connectivity()
        
        self.assertTrue(result)
        mock_run.assert_called()
    
    @patch('subprocess.run')
    def test_check_connectivity_failure(self, mock_run):
        """Test failed connectivity check."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result
        
        result = self.timeout_manager._check_connectivity()
        
        self.assertFalse(result)
    
    @patch('socket.inet_aton')
    def test_is_ip_address(self, mock_inet_aton):
        """Test IP address detection."""
        # Valid IP
        mock_inet_aton.return_value = b'\x08\x08\x08\x08'
        result = self.timeout_manager._is_ip_address('8.8.8.8')
        self.assertTrue(result)
        
        # Invalid IP (hostname)
        mock_inet_aton.side_effect = OSError()
        result = self.timeout_manager._is_ip_address('google.com')
        self.assertFalse(result)
    
    def test_cancel_timeout(self):
        """Test cancelling a specific timeout."""
        # Start a timeout
        self.timeout_manager.start_timeout(
            change_id="test_123",
            file_path="/etc/test/config",
            change_category="network"
        )
        
        # Cancel it
        success = self.timeout_manager.cancel_timeout("test_123")
        
        self.assertTrue(success)
        self.assertNotIn("test_123", self.timeout_manager.active_timeouts)
    
    def test_cancel_unknown_timeout(self):
        """Test cancelling unknown timeout."""
        success = self.timeout_manager.cancel_timeout("unknown_123")
        self.assertFalse(success)
    
    def test_cancel_all_timeouts(self):
        """Test cancelling all timeouts."""
        # Start multiple timeouts
        for i in range(3):
            self.timeout_manager.start_timeout(
                change_id=f"test_{i}",
                file_path=f"/etc/test/config{i}",
                change_category="network"
            )
        
        # Cancel all
        count = self.timeout_manager.cancel_all_timeouts()
        
        self.assertEqual(count, 3)
        self.assertEqual(len(self.timeout_manager.active_timeouts), 0)
    
    @patch('time.sleep')  # Speed up test
    def test_handle_timeout_expiry(self, mock_sleep):
        """Test handling timeout expiry."""
        # Mock revert engine
        self.mock_revert_engine.revert_change.return_value = True
        
        # Create an expired timeout entry manually
        entry = TimeoutEntry(
            change_id="test_123",
            file_path="/etc/test/config",
            change_category="network",
            snapshot_id="snap_123",
            event_type="modified",
            timeout_seconds=1,  # Very short timeout
            start_time=datetime.now() - timedelta(seconds=2)  # Already expired
        )
        
        self.timeout_manager.active_timeouts["test_123"] = entry
        
        # Trigger expiry handling
        self.timeout_manager._handle_timeout_expiry("test_123")
        
        # Should have called revert
        self.mock_revert_engine.revert_change.assert_called_once_with(
            file_path="/etc/test/config",
            change_category="network",
            snapshot_id="snap_123"
        )
        
        # Should have removed from active timeouts
        self.assertNotIn("test_123", self.timeout_manager.active_timeouts)
    
    def test_format_notification_message(self):
        """Test notification message formatting."""
        entry = TimeoutEntry(
            change_id="test_123",
            file_path="/etc/test/config",
            change_category="network",
            snapshot_id="snap_123",
            event_type="modified",
            timeout_seconds=300,
            start_time=datetime.now()
        )
        
        # Test different event types
        msg = self.timeout_manager._format_notification_message(entry, 'started')
        self.assertIn('/etc/test/config', msg)
        self.assertIn('300s timeout', msg)
        
        msg = self.timeout_manager._format_notification_message(entry, 'confirmed')
        self.assertIn('confirmed', msg)
        
        msg = self.timeout_manager._format_notification_message(entry, 'expired')
        self.assertIn('EXPIRED', msg)
        self.assertIn('revert', msg)


if __name__ == '__main__':
    unittest.main()