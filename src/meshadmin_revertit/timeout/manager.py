#!/usr/bin/env python3
"""
Timeout Manager - Handles timed confirmations for configuration changes.
"""

import time
import threading
import logging
import subprocess
import socket
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from queue import Queue, Empty


class TimeoutEntry:
    """Represents a single timeout entry."""
    
    def __init__(self, change_id: str, file_path: str, change_category: str,
                 snapshot_id: Optional[str], event_type: str, timeout_seconds: int,
                 start_time: datetime):
        """Initialize timeout entry."""
        self.change_id = change_id
        self.file_path = file_path
        self.change_category = change_category
        self.snapshot_id = snapshot_id
        self.event_type = event_type
        self.timeout_seconds = timeout_seconds
        self.start_time = start_time
    
    def is_expired(self, current_time: datetime) -> bool:
        """Check if timeout has expired."""
        expiry_time = self.start_time + timedelta(seconds=self.timeout_seconds)
        return current_time >= expiry_time
    
    def get_remaining_time(self, current_time: datetime) -> timedelta:
        """Get remaining time until timeout expiry."""
        expiry_time = self.start_time + timedelta(seconds=self.timeout_seconds)
        remaining = expiry_time - current_time
        return remaining if remaining.total_seconds() > 0 else timedelta(0)


class TimeoutManager:
    """Manages timeout confirmations for configuration changes."""
    
    def __init__(self, config: Dict[str, Any], revert_engine):
        """Initialize timeout manager."""
        self.config = config
        self.revert_engine = revert_engine
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.default_timeout = config.get('timeout_action', 'revert')
        self.connectivity_check = config.get('connectivity_check', True)
        self.connectivity_endpoints = config.get('connectivity_endpoints', ['8.8.8.8', '1.1.1.1'])
        self.connectivity_timeout = config.get('connectivity_timeout', 10)
        self.grace_period = config.get('revert_grace_period', 30)
        
        # Active timeouts tracking
        self.active_timeouts: Dict[str, TimeoutEntry] = {}
        self.timeout_queue: Queue = Queue()
        
        # Threading
        self.running = False
        self.processor_thread: Optional[threading.Thread] = None
        self.lock = threading.RLock()
        
        self.logger.info("Timeout manager initialized")
    
    def start_timeout(self, change_id: str, file_path: str, change_category: str, 
                     snapshot_id: Optional[str] = None, event_type: str = "modified",
                     timeout_seconds: Optional[int] = None) -> bool:
        """Start a timeout for a configuration change."""
        
        if timeout_seconds is None:
            timeout_seconds = self._get_timeout_for_category(change_category)
        
        # Validate timeout bounds
        min_timeout = 60  # 1 minute minimum
        max_timeout = 1800  # 30 minutes maximum
        timeout_seconds = max(min_timeout, min(max_timeout, timeout_seconds))
        
        timeout_entry = TimeoutEntry(
            change_id=change_id,
            file_path=file_path,
            change_category=change_category,
            snapshot_id=snapshot_id,
            event_type=event_type,
            timeout_seconds=timeout_seconds,
            start_time=datetime.now()
        )
        
        with self.lock:
            # Cancel any existing timeout for the same file
            existing_entries = [
                entry_id for entry_id, entry in self.active_timeouts.items()
                if entry.file_path == file_path
            ]
            
            for entry_id in existing_entries:
                self.logger.info(f"Cancelling existing timeout for {file_path}: {entry_id}")
                del self.active_timeouts[entry_id]
            
            # Add new timeout
            self.active_timeouts[change_id] = timeout_entry
            self.timeout_queue.put(change_id)
        
        self.logger.info(f"Started timeout for {change_category} change: {file_path} "
                        f"(timeout: {timeout_seconds}s, change_id: {change_id})")
        
        # Send notification about pending change
        self._send_timeout_notification(timeout_entry, "started")
        
        return True
    
    def _get_timeout_for_category(self, category: str) -> int:
        """Get appropriate timeout duration for change category."""
        # Critical changes get longer timeouts
        category_timeouts = {
            'network': 600,   # 10 minutes for network changes
            'ssh': 900,       # 15 minutes for SSH changes
            'firewall': 300,  # 5 minutes for firewall changes
            'service': 300,   # 5 minutes for service changes
            'system': 300     # 5 minutes for other system changes
        }
        
        return category_timeouts.get(category, 300)  # Default 5 minutes
    
    def confirm_change(self, change_id: str) -> bool:
        """Confirm a configuration change, cancelling its timeout."""
        with self.lock:
            if change_id not in self.active_timeouts:
                self.logger.warning(f"Cannot confirm unknown change: {change_id}")
                return False
            
            timeout_entry = self.active_timeouts[change_id]
            del self.active_timeouts[change_id]
        
        self.logger.info(f"Configuration change confirmed: {change_id} ({timeout_entry.file_path})")
        
        # Send notification about confirmation
        self._send_timeout_notification(timeout_entry, "confirmed")
        
        # Clean up old snapshots if configured
        if timeout_entry.snapshot_id:
            try:
                # Keep the snapshot for a while in case we need to revert later
                # Actual cleanup will be handled by snapshot manager's cleanup routine
                pass
            except Exception as e:
                self.logger.warning(f"Error during snapshot cleanup: {e}")
        
        return True
    
    def list_active_timeouts(self) -> List[Dict[str, Any]]:
        """List all active timeouts."""
        with self.lock:
            timeouts = []
            current_time = datetime.now()
            
            for change_id, entry in self.active_timeouts.items():
                remaining_time = entry.get_remaining_time(current_time)
                
                timeouts.append({
                    'change_id': change_id,
                    'file_path': entry.file_path,
                    'change_category': entry.change_category,
                    'event_type': entry.event_type,
                    'start_time': entry.start_time.isoformat(),
                    'timeout_seconds': entry.timeout_seconds,
                    'remaining_seconds': max(0, int(remaining_time.total_seconds())),
                    'snapshot_id': entry.snapshot_id
                })
            
            return timeouts
    
    def start_processing(self) -> None:
        """Start the timeout processing thread."""
        if self.running:
            self.logger.warning("Timeout processor is already running")
            return
        
        self.logger.info("Starting timeout processor")
        self.running = True
        
        try:
            while self.running:
                try:
                    # Process timeout queue with a short timeout
                    change_id = self.timeout_queue.get(timeout=1)
                    self._process_timeout(change_id)
                except Empty:
                    # Check for expired timeouts
                    self._check_expired_timeouts()
                except Exception as e:
                    self.logger.error(f"Error in timeout processor: {e}")
        except KeyboardInterrupt:
            self.logger.info("Timeout processor interrupted")
        finally:
            self.running = False
    
    def _process_timeout(self, change_id: str) -> None:
        """Process a timeout entry."""
        with self.lock:
            if change_id not in self.active_timeouts:
                return  # Already processed or confirmed
            
            entry = self.active_timeouts[change_id]
        
        # Wait for the timeout period
        end_time = entry.start_time + timedelta(seconds=entry.timeout_seconds)
        
        while datetime.now() < end_time and self.running:
            with self.lock:
                if change_id not in self.active_timeouts:
                    return  # Confirmed or cancelled
            
            time.sleep(1)
        
        # Timeout expired, check if we should revert
        if self.running:
            self._handle_timeout_expiry(change_id)
    
    def _check_expired_timeouts(self) -> None:
        """Check for and handle expired timeouts."""
        current_time = datetime.now()
        expired_entries = []
        
        with self.lock:
            for change_id, entry in self.active_timeouts.items():
                if entry.is_expired(current_time):
                    expired_entries.append(change_id)
        
        for change_id in expired_entries:
            self._handle_timeout_expiry(change_id)
    
    def _handle_timeout_expiry(self, change_id: str) -> None:
        """Handle timeout expiry for a configuration change."""
        with self.lock:
            if change_id not in self.active_timeouts:
                return  # Already processed
            
            entry = self.active_timeouts[change_id]
            del self.active_timeouts[change_id]
        
        self.logger.warning(f"Configuration change timeout expired: {change_id} ({entry.file_path})")
        
        # Send notification about expiry
        self._send_timeout_notification(entry, "expired")
        
        # Check connectivity if enabled
        if self.connectivity_check:
            if self._check_connectivity():
                self.logger.info("Connectivity check passed, but timeout expired - proceeding with revert")
            else:
                self.logger.warning("Connectivity check failed - configuration change may have broken connectivity")
        
        # Grace period before revert
        if self.grace_period > 0:
            self.logger.info(f"Grace period of {self.grace_period} seconds before revert")
            self._send_timeout_notification(entry, "grace_period")
            
            # Wait for grace period, checking for late confirmation
            grace_end = time.time() + self.grace_period
            while time.time() < grace_end and self.running:
                time.sleep(1)
        
        # Perform revert
        self._perform_revert(entry)
    
    def _check_connectivity(self) -> bool:
        """Check network connectivity to configured endpoints."""
        self.logger.debug("Checking network connectivity")
        
        for endpoint in self.connectivity_endpoints:
            if self._test_connectivity(endpoint):
                self.logger.debug(f"Connectivity check passed: {endpoint}")
                return True
        
        self.logger.warning("All connectivity checks failed")
        return False
    
    def _test_connectivity(self, endpoint: str) -> bool:
        """Test connectivity to a specific endpoint."""
        try:
            # Try DNS resolution first
            if not self._is_ip_address(endpoint):
                socket.gethostbyname(endpoint)
            
            # Try ping
            result = subprocess.run([
                'ping', '-c', '1', '-W', str(self.connectivity_timeout), endpoint
            ], capture_output=True, text=True, timeout=self.connectivity_timeout + 5)
            
            return result.returncode == 0
            
        except Exception as e:
            self.logger.debug(f"Connectivity test failed for {endpoint}: {e}")
            return False
    
    def _is_ip_address(self, address: str) -> bool:
        """Check if string is an IP address."""
        try:
            socket.inet_aton(address)
            return True
        except socket.error:
            return False
    
    def _perform_revert(self, entry: TimeoutEntry) -> None:
        """Perform automatic revert of configuration change."""
        self.logger.info(f"Performing automatic revert for: {entry.file_path}")
        
        try:
            success = self.revert_engine.revert_change(
                file_path=entry.file_path,
                change_category=entry.change_category,
                snapshot_id=entry.snapshot_id
            )
            
            if success:
                self.logger.info(f"Successfully reverted: {entry.file_path}")
                self._send_timeout_notification(entry, "reverted")
            else:
                self.logger.error(f"Failed to revert: {entry.file_path}")
                self._send_timeout_notification(entry, "revert_failed")
                
        except Exception as e:
            self.logger.error(f"Error during revert of {entry.file_path}: {e}")
            self._send_timeout_notification(entry, "revert_error")
    
    def _send_timeout_notification(self, entry: TimeoutEntry, event_type: str) -> None:
        """Send notification about timeout event."""
        message = self._format_notification_message(entry, event_type)
        
        # Log the notification
        if event_type in ['expired', 'revert_failed', 'revert_error']:
            self.logger.error(message)
        elif event_type in ['started', 'grace_period']:
            self.logger.warning(message)
        else:
            self.logger.info(message)
        
        # Additional notification mechanisms can be added here
        # (email, desktop notifications, etc.)
    
    def _format_notification_message(self, entry: TimeoutEntry, event_type: str) -> str:
        """Format notification message for timeout event."""
        messages = {
            'started': f"Configuration change timeout started: {entry.file_path} "
                      f"({entry.timeout_seconds}s timeout)",
            'confirmed': f"Configuration change confirmed: {entry.file_path}",
            'expired': f"Configuration change timeout EXPIRED: {entry.file_path} "
                      f"- automatic revert will be performed",
            'grace_period': f"Grace period before revert: {entry.file_path} "
                           f"({self.grace_period}s remaining)",
            'reverted': f"Configuration change successfully reverted: {entry.file_path}",
            'revert_failed': f"CRITICAL: Failed to revert configuration change: {entry.file_path}",
            'revert_error': f"CRITICAL: Error during revert of configuration change: {entry.file_path}"
        }
        
        return messages.get(event_type, f"Timeout event ({event_type}): {entry.file_path}")
    
    def stop_processing(self) -> None:
        """Stop the timeout processing thread."""
        self.logger.info("Stopping timeout processor")
        self.running = False
    
    def cancel_timeout(self, change_id: str) -> bool:
        """Cancel a specific timeout."""
        with self.lock:
            if change_id in self.active_timeouts:
                entry = self.active_timeouts[change_id]
                del self.active_timeouts[change_id]
                self.logger.info(f"Cancelled timeout: {change_id} ({entry.file_path})")
                return True
            else:
                self.logger.warning(f"Cannot cancel unknown timeout: {change_id}")
                return False
    
    def cancel_all_timeouts(self) -> int:
        """Cancel all active timeouts."""
        with self.lock:
            count = len(self.active_timeouts)
            self.active_timeouts.clear()
            self.logger.info(f"Cancelled all timeouts ({count} entries)")
            return count