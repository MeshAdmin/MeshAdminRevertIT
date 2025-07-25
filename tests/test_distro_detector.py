#!/usr/bin/env python3
"""
Tests for DistroDetector functionality.
"""

import unittest
from unittest.mock import patch, mock_open, MagicMock
import tempfile
import os

from meshadmin_revertit.distro.detector import DistroDetector


class TestDistroDetector(unittest.TestCase):
    """Test cases for DistroDetector."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.config = {
            'auto_detect': True,
            'force_distro': None
        }
        self.detector = DistroDetector(self.config)
    
    def test_init(self):
        """Test DistroDetector initialization."""
        self.assertEqual(self.detector.config, self.config)
        self.assertTrue(self.detector.auto_detect)
        self.assertIsNone(self.detector.force_distro)
        self.assertIsNone(self.detector._cached_info)
    
    def test_forced_distro(self):
        """Test forced distribution detection."""
        config = {
            'auto_detect': True,
            'force_distro': 'ubuntu'
        }
        detector = DistroDetector(config)
        
        info = detector.detect()
        
        self.assertEqual(info['id'], 'ubuntu')
        self.assertEqual(info['name'], 'Ubuntu')
        self.assertEqual(info['family'], 'debian')
        self.assertEqual(info['package_manager'], 'apt')
        self.assertEqual(info['detection_method'], 'forced')
    
    def test_forced_unknown_distro(self):
        """Test forced unknown distribution."""
        config = {
            'auto_detect': True,
            'force_distro': 'unknowndistro'
        }
        detector = DistroDetector(config)
        
        info = detector.detect()
        
        self.assertEqual(info['id'], 'unknowndistro')
        self.assertEqual(info['name'], 'unknowndistro')
        self.assertEqual(info['family'], 'unknown')
        self.assertEqual(info['package_manager'], 'unknown')
        self.assertEqual(info['detection_method'], 'forced_unknown')
    
    @patch('builtins.open', new_callable=mock_open, read_data='''ID=ubuntu
NAME="Ubuntu"
VERSION="20.04.3 LTS (Focal Fossa)"
VERSION_ID="20.04"
VERSION_CODENAME=focal
ID_LIKE=debian''')
    @patch('os.path.exists')
    def test_detect_from_os_release(self, mock_exists, mock_file):
        """Test detection from /etc/os-release."""
        mock_exists.return_value = True
        
        info = self.detector._detect_from_os_release()
        
        self.assertIsNotNone(info)
        self.assertEqual(info['id'], 'ubuntu')
        self.assertEqual(info['name'], 'Ubuntu')
        self.assertEqual(info['version'], '20.04')
        self.assertEqual(info['family'], 'debian')
        self.assertEqual(info['package_manager'], 'apt')
        self.assertEqual(info['detection_method'], 'os_release')
    
    @patch('subprocess.run')
    def test_detect_from_lsb_release(self, mock_run):
        """Test detection from lsb_release command."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '''Distributor ID: Ubuntu
Description:    Ubuntu 20.04.3 LTS
Release:        20.04
Codename:       focal'''
        mock_run.return_value = mock_result
        
        info = self.detector._detect_from_lsb_release()
        
        self.assertIsNotNone(info)
        self.assertEqual(info['id'], 'ubuntu')
        self.assertEqual(info['name'], 'Ubuntu')
        self.assertEqual(info['version'], '20.04')
        self.assertEqual(info['family'], 'debian')
        self.assertEqual(info['detection_method'], 'lsb_release')
    
    @patch('builtins.open', new_callable=mock_open, read_data='Ubuntu 20.04.3 LTS')
    @patch('os.path.exists')
    def test_detect_from_issue(self, mock_exists, mock_file):
        """Test detection from /etc/issue."""
        mock_exists.return_value = True
        
        info = self.detector._detect_from_issue()
        
        self.assertIsNotNone(info)
        self.assertEqual(info['id'], 'ubuntu')
        self.assertEqual(info['name'], 'Ubuntu')
        self.assertEqual(info['family'], 'debian')
        self.assertEqual(info['detection_method'], 'issue')
    
    @patch('os.path.exists')
    @patch('builtins.open', new_callable=mock_open, read_data='10.0')
    def test_detect_from_system_files(self, mock_file, mock_exists):
        """Test detection from system-specific files."""
        def exists_side_effect(path):
            return path == '/etc/debian_version'
        
        mock_exists.side_effect = exists_side_effect
        
        info = self.detector._detect_from_system_files()
        
        self.assertIsNotNone(info)
        self.assertEqual(info['id'], 'debian')
        self.assertEqual(info['name'], 'Debian')
        self.assertEqual(info['version'], '10')
        self.assertEqual(info['family'], 'debian')
        self.assertEqual(info['detection_method'], 'system_files')
    
    @patch('subprocess.run')
    def test_detect_from_package_managers(self, mock_run):
        """Test detection from package managers."""
        # Mock successful apt detection
        def run_side_effect(cmd, **kwargs):
            if cmd == ['which', 'apt']:
                result = MagicMock()
                result.returncode = 0
                return result
            else:
                result = MagicMock()
                result.returncode = 1
                return result
        
        mock_run.side_effect = run_side_effect
        
        info = self.detector._detect_from_package_managers()
        
        self.assertIsNotNone(info)
        self.assertEqual(info['id'], 'ubuntu')
        self.assertEqual(info['package_manager'], 'apt')
        self.assertEqual(info['family'], 'debian')
        self.assertEqual(info['detection_method'], 'package_manager')
    
    def test_determine_family(self):
        """Test family determination logic."""
        # Test ID_LIKE based detection
        family = self.detector._determine_family('debian ubuntu', 'mint')
        self.assertEqual(family, 'debian')
        
        family = self.detector._determine_family('rhel fedora', 'centos')
        self.assertEqual(family, 'rhel')
        
        # Test distribution ID based detection
        family = self.detector._determine_family('', 'ubuntu')
        self.assertEqual(family, 'debian')
        
        family = self.detector._determine_family('', 'fedora')
        self.assertEqual(family, 'rhel')
        
        family = self.detector._determine_family('', 'arch')
        self.assertEqual(family, 'arch')
        
        # Test unknown
        family = self.detector._determine_family('', 'unknown')
        self.assertEqual(family, 'unknown')
    
    def test_determine_package_manager(self):
        """Test package manager determination."""
        pm = self.detector._determine_package_manager('ubuntu')
        self.assertEqual(pm, 'apt')
        
        pm = self.detector._determine_package_manager('fedora')
        self.assertEqual(pm, 'dnf')
        
        pm = self.detector._determine_package_manager('centos')
        self.assertEqual(pm, 'yum')
        
        pm = self.detector._determine_package_manager('arch')
        self.assertEqual(pm, 'pacman')
        
        pm = self.detector._determine_package_manager('unknown')
        self.assertEqual(pm, 'unknown')
    
    @patch('os.path.exists')
    def test_determine_init_system(self, mock_exists):
        """Test init system determination."""
        # Test systemd detection
        def exists_side_effect(path):
            return path == '/run/systemd/system'
        
        mock_exists.side_effect = exists_side_effect
        
        init_system = self.detector._determine_init_system()
        self.assertEqual(init_system, 'systemd')
        
        # Test SysV detection
        def exists_side_effect_sysv(path):
            return path == '/etc/init.d'
        
        mock_exists.side_effect = exists_side_effect_sysv
        
        init_system = self.detector._determine_init_system()
        self.assertEqual(init_system, 'sysv')
    
    def test_get_compatibility_info(self):
        """Test compatibility information retrieval."""
        # Mock detection result
        self.detector._cached_info = {
            'id': 'ubuntu',
            'name': 'Ubuntu',
            'family': 'debian',
            'init_system': 'systemd',
            'package_manager': 'apt'
        }
        
        compat = self.detector.get_compatibility_info()
        
        self.assertIn('supported', compat)
        self.assertIn('timeshift_available', compat)
        self.assertIn('service_management', compat)
        self.assertIn('network_management', compat)
        self.assertIn('firewall_management', compat)
        self.assertIn('package_management', compat)
        
        self.assertTrue(compat['supported'])
        self.assertTrue(compat['timeshift_available'])
        self.assertEqual(compat['service_management']['system'], 'systemd')
        self.assertEqual(compat['package_management']['manager'], 'apt')
    
    def test_is_supported(self):
        """Test distribution support checking."""
        # Mock systemd system
        self.detector._cached_info = {
            'init_system': 'systemd'
        }
        
        self.assertTrue(self.detector.is_supported())
        
        # Mock SysV system
        self.detector._cached_info = {
            'init_system': 'sysv'
        }
        
        self.assertTrue(self.detector.is_supported())
        
        # Mock unknown system
        self.detector._cached_info = {
            'init_system': 'unknown'
        }
        
        self.assertFalse(self.detector.is_supported())
    
    def test_caching(self):
        """Test that detection results are cached."""
        # Mock a detection method
        with patch.object(self.detector, '_auto_detect_distro') as mock_detect:
            mock_detect.return_value = {
                'id': 'ubuntu',
                'name': 'Ubuntu',
                'family': 'debian'
            }
            
            # First call should trigger detection
            info1 = self.detector.detect()
            self.assertEqual(mock_detect.call_count, 1)
            
            # Second call should use cache
            info2 = self.detector.detect()
            self.assertEqual(mock_detect.call_count, 1)
            
            # Results should be identical
            self.assertEqual(info1, info2)


if __name__ == '__main__':
    unittest.main()