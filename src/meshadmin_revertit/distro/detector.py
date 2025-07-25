#!/usr/bin/env python3
"""
Distribution Detector - Detects Linux distribution and provides compatibility information.
"""

import os
import subprocess
import logging
from typing import Dict, Optional, List, Any


class DistroDetector:
    """Detects Linux distribution and provides compatibility information."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize distribution detector."""
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        self.force_distro = config.get('force_distro')
        self.auto_detect = config.get('auto_detect', True)
        
        # Cached detection result
        self._cached_info: Optional[Dict[str, str]] = None
        
        self.logger.debug("Distribution detector initialized")
    
    def detect(self) -> Dict[str, str]:
        """Detect the current Linux distribution."""
        if self._cached_info:
            return self._cached_info
        
        # Use forced distribution if specified
        if self.force_distro:
            self.logger.info(f"Using forced distribution: {self.force_distro}")
            self._cached_info = self._get_forced_distro_info()
            return self._cached_info
        
        # Auto-detect if enabled
        if self.auto_detect:
            self._cached_info = self._auto_detect_distro()
        else:
            # Default to Ubuntu if auto-detection is disabled
            self._cached_info = self._get_default_distro_info()
        
        self.logger.info(f"Detected distribution: {self._cached_info}")
        return self._cached_info
    
    def _get_forced_distro_info(self) -> Dict[str, str]:
        """Get information for forced distribution."""
        distro_id = self.force_distro.lower()
        
        # Get basic info from known distributions
        known_distros = self._get_known_distros()
        
        if distro_id in known_distros:
            info = known_distros[distro_id].copy()
            info['detection_method'] = 'forced'
            return info
        else:
            # Unknown forced distribution
            return {
                'id': distro_id,
                'name': self.force_distro,
                'version': 'unknown',
                'family': 'unknown',
                'package_manager': 'unknown',
                'init_system': 'systemd',
                'detection_method': 'forced_unknown'
            }
    
    def _get_default_distro_info(self) -> Dict[str, str]:
        """Get default distribution information (Ubuntu)."""
        return {
            'id': 'ubuntu',
            'name': 'Ubuntu',
            'version': 'unknown',
            'family': 'debian',
            'package_manager': 'apt',
            'init_system': 'systemd',
            'detection_method': 'default'
        }
    
    def _auto_detect_distro(self) -> Dict[str, str]:
        """Auto-detect Linux distribution."""
        # Try multiple detection methods
        detection_methods = [
            self._detect_from_os_release,
            self._detect_from_lsb_release,
            self._detect_from_issue,
            self._detect_from_system_files,
            self._detect_from_package_managers
        ]
        
        for method in detection_methods:
            try:
                info = method()
                if info:
                    return info
            except Exception as e:
                self.logger.debug(f"Detection method failed: {method.__name__}: {e}")
        
        # Fallback to default
        self.logger.warning("Could not detect distribution, using default (Ubuntu)")
        info = self._get_default_distro_info()
        info['detection_method'] = 'fallback'
        return info
    
    def _detect_from_os_release(self) -> Optional[Dict[str, str]]:
        """Detect distribution from /etc/os-release."""
        os_release_files = ['/etc/os-release', '/usr/lib/os-release']
        
        for file_path in os_release_files:
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'r') as f:
                        lines = f.readlines()
                    
                    info = {}
                    for line in lines:
                        line = line.strip()
                        if '=' in line:
                            key, value = line.split('=', 1)
                            info[key] = value.strip('"\'')
                    
                    # Map os-release fields to our format
                    distro_info = {
                        'id': info.get('ID', 'unknown').lower(),
                        'name': info.get('NAME', 'Unknown'),
                        'version': info.get('VERSION_ID', 'unknown'),
                        'version_name': info.get('VERSION', 'unknown'),
                        'family': self._determine_family(info.get('ID_LIKE', ''), info.get('ID', '')),
                        'package_manager': self._determine_package_manager(info.get('ID', '')),
                        'init_system': self._determine_init_system(),
                        'detection_method': 'os_release'
                    }
                    
                    self.logger.debug(f"Detected from os-release: {distro_info}")
                    return distro_info
                    
                except Exception as e:
                    self.logger.debug(f"Failed to parse {file_path}: {e}")
        
        return None
    
    def _detect_from_lsb_release(self) -> Optional[Dict[str, str]]:
        """Detect distribution from lsb_release command."""
        try:
            result = subprocess.run(['lsb_release', '-a'], 
                                  capture_output=True, text=True, check=True)
            
            lines = result.stdout.split('\n')
            info = {}
            
            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    info[key.strip()] = value.strip()
            
            distro_info = {
                'id': info.get('Distributor ID', 'unknown').lower(),
                'name': info.get('Distributor ID', 'Unknown'),
                'version': info.get('Release', 'unknown'),
                'version_name': info.get('Description', 'unknown'),
                'family': self._determine_family('', info.get('Distributor ID', '')),
                'package_manager': self._determine_package_manager(info.get('Distributor ID', '')),
                'init_system': self._determine_init_system(),
                'detection_method': 'lsb_release'
            }
            
            self.logger.debug(f"Detected from lsb_release: {distro_info}")
            return distro_info
            
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
    
    def _detect_from_issue(self) -> Optional[Dict[str, str]]:
        """Detect distribution from /etc/issue."""
        try:
            with open('/etc/issue', 'r') as f:
                issue_content = f.read().strip()
            
            # Parse common issue formats
            issue_lower = issue_content.lower()
            
            distro_id = 'unknown'
            name = 'Unknown'
            
            if 'ubuntu' in issue_lower:
                distro_id = 'ubuntu'
                name = 'Ubuntu'
            elif 'debian' in issue_lower:
                distro_id = 'debian'
                name = 'Debian'
            elif 'centos' in issue_lower:
                distro_id = 'centos'
                name = 'CentOS'
            elif 'rhel' in issue_lower or 'red hat' in issue_lower:
                distro_id = 'rhel'
                name = 'Red Hat Enterprise Linux'
            elif 'fedora' in issue_lower:
                distro_id = 'fedora'
                name = 'Fedora'
            elif 'arch' in issue_lower:
                distro_id = 'arch'
                name = 'Arch Linux'
            
            if distro_id != 'unknown':
                distro_info = {
                    'id': distro_id,
                    'name': name,
                    'version': 'unknown',
                    'family': self._determine_family('', distro_id),
                    'package_manager': self._determine_package_manager(distro_id),
                    'init_system': self._determine_init_system(),
                    'detection_method': 'issue'
                }
                
                self.logger.debug(f"Detected from /etc/issue: {distro_info}")
                return distro_info
        
        except Exception as e:
            self.logger.debug(f"Failed to read /etc/issue: {e}")
        
        return None
    
    def _detect_from_system_files(self) -> Optional[Dict[str, str]]:
        """Detect distribution from system-specific files."""
        system_files = {
            '/etc/debian_version': ('debian', 'Debian'),
            '/etc/redhat-release': ('rhel', 'Red Hat Enterprise Linux'),
            '/etc/centos-release': ('centos', 'CentOS'),
            '/etc/fedora-release': ('fedora', 'Fedora'),
            '/etc/arch-release': ('arch', 'Arch Linux'),
            '/etc/gentoo-release': ('gentoo', 'Gentoo'),
            '/etc/SuSE-release': ('opensuse', 'openSUSE'),
            '/etc/mandriva-release': ('mandriva', 'Mandriva')
        }
        
        for file_path, (distro_id, name) in system_files.items():
            if os.path.exists(file_path):
                try:
                    # Try to extract version information
                    version = 'unknown'
                    with open(file_path, 'r') as f:
                        content = f.read().strip()
                        # Simple version extraction
                        import re
                        version_match = re.search(r'(\d+\.?\d*)', content)
                        if version_match:
                            version = version_match.group(1)
                    
                    distro_info = {
                        'id': distro_id,
                        'name': name,
                        'version': version,
                        'family': self._determine_family('', distro_id),
                        'package_manager': self._determine_package_manager(distro_id),
                        'init_system': self._determine_init_system(),
                        'detection_method': 'system_files'
                    }
                    
                    self.logger.debug(f"Detected from {file_path}: {distro_info}")
                    return distro_info
                    
                except Exception as e:
                    self.logger.debug(f"Failed to read {file_path}: {e}")
        
        return None
    
    def _detect_from_package_managers(self) -> Optional[Dict[str, str]]:
        """Detect distribution from available package managers."""
        package_managers = {
            'apt': ('ubuntu', 'Ubuntu', 'debian'),
            'yum': ('rhel', 'Red Hat Enterprise Linux', 'rhel'),
            'dnf': ('fedora', 'Fedora', 'rhel'),
            'pacman': ('arch', 'Arch Linux', 'arch'),
            'zypper': ('opensuse', 'openSUSE', 'suse'),
            'emerge': ('gentoo', 'Gentoo', 'gentoo'),
            'apk': ('alpine', 'Alpine Linux', 'alpine')
        }
        
        for pm_cmd, (distro_id, name, family) in package_managers.items():
            try:
                subprocess.run(['which', pm_cmd], 
                             capture_output=True, check=True)
                
                distro_info = {
                    'id': distro_id,
                    'name': name,
                    'version': 'unknown',
                    'family': family,
                    'package_manager': pm_cmd,
                    'init_system': self._determine_init_system(),
                    'detection_method': 'package_manager'
                }
                
                self.logger.debug(f"Detected from package manager {pm_cmd}: {distro_info}")
                return distro_info
                
            except subprocess.CalledProcessError:
                continue
        
        return None
    
    def _determine_family(self, id_like: str, distro_id: str) -> str:
        """Determine distribution family."""
        id_like_lower = id_like.lower()
        distro_id_lower = distro_id.lower()
        
        # Check ID_LIKE first
        if 'debian' in id_like_lower or 'ubuntu' in id_like_lower:
            return 'debian'
        elif 'rhel' in id_like_lower or 'fedora' in id_like_lower:
            return 'rhel'
        elif 'arch' in id_like_lower:
            return 'arch'
        elif 'suse' in id_like_lower:
            return 'suse'
        
        # Check distribution ID
        if distro_id_lower in ['ubuntu', 'debian', 'mint', 'elementary']:
            return 'debian'
        elif distro_id_lower in ['rhel', 'centos', 'fedora', 'rocky', 'alma']:
            return 'rhel'
        elif distro_id_lower in ['arch', 'manjaro', 'antergos']:
            return 'arch'
        elif distro_id_lower in ['opensuse', 'sles']:
            return 'suse'
        elif distro_id_lower in ['gentoo']:
            return 'gentoo'
        elif distro_id_lower in ['alpine']:
            return 'alpine'
        
        return 'unknown'
    
    def _determine_package_manager(self, distro_id: str) -> str:
        """Determine package manager for distribution."""
        distro_id_lower = distro_id.lower()
        
        # Map distributions to package managers
        pm_map = {
            'ubuntu': 'apt',
            'debian': 'apt',
            'mint': 'apt',
            'elementary': 'apt',
            'rhel': 'yum',
            'centos': 'yum',
            'rocky': 'yum',
            'alma': 'yum',
            'fedora': 'dnf',
            'arch': 'pacman',
            'manjaro': 'pacman',
            'antergos': 'pacman',
            'opensuse': 'zypper',
            'sles': 'zypper',
            'gentoo': 'emerge',
            'alpine': 'apk'
        }
        
        return pm_map.get(distro_id_lower, 'unknown')
    
    def _determine_init_system(self) -> str:
        """Determine init system."""
        # Check for systemd
        if os.path.exists('/run/systemd/system'):
            return 'systemd'
        
        # Check for SysV init
        if os.path.exists('/etc/init.d'):
            return 'sysv'
        
        # Check for Upstart
        if os.path.exists('/etc/init') and os.path.isdir('/etc/init'):
            return 'upstart'
        
        # Check for OpenRC
        if os.path.exists('/etc/runlevels'):
            return 'openrc'
        
        # Default assumption
        return 'systemd'
    
    def _get_known_distros(self) -> Dict[str, Dict[str, str]]:
        """Get information about known distributions."""
        return {
            'ubuntu': {
                'id': 'ubuntu',
                'name': 'Ubuntu',
                'family': 'debian',
                'package_manager': 'apt',
                'init_system': 'systemd'
            },
            'debian': {
                'id': 'debian',
                'name': 'Debian',
                'family': 'debian',
                'package_manager': 'apt',
                'init_system': 'systemd'
            },
            'centos': {
                'id': 'centos',
                'name': 'CentOS',
                'family': 'rhel',
                'package_manager': 'yum',
                'init_system': 'systemd'
            },
            'rhel': {
                'id': 'rhel',
                'name': 'Red Hat Enterprise Linux',
                'family': 'rhel',
                'package_manager': 'yum',
                'init_system': 'systemd'
            },
            'fedora': {
                'id': 'fedora',
                'name': 'Fedora',
                'family': 'rhel',
                'package_manager': 'dnf',
                'init_system': 'systemd'
            },
            'arch': {
                'id': 'arch',
                'name': 'Arch Linux',
                'family': 'arch',
                'package_manager': 'pacman',
                'init_system': 'systemd'
            },
            'opensuse': {
                'id': 'opensuse',
                'name': 'openSUSE',
                'family': 'suse',
                'package_manager': 'zypper',
                'init_system': 'systemd'
            },
            'alpine': {
                'id': 'alpine',
                'name': 'Alpine Linux',
                'family': 'alpine',
                'package_manager': 'apk',
                'init_system': 'openrc'
            }
        }
    
    def get_compatibility_info(self) -> Dict[str, Any]:
        """Get compatibility information for the detected distribution."""
        distro_info = self.detect()
        
        compatibility = {
            'supported': True,
            'timeshift_available': self._check_timeshift_compatibility(distro_info),
            'service_management': self._get_service_management_info(distro_info),
            'network_management': self._get_network_management_info(distro_info),
            'firewall_management': self._get_firewall_management_info(distro_info),
            'package_management': self._get_package_management_info(distro_info)
        }
        
        return compatibility
    
    def _check_timeshift_compatibility(self, distro_info: Dict[str, str]) -> bool:
        """Check if TimeShift is compatible with the distribution."""
        # TimeShift works best with systemd-based distributions
        if distro_info['init_system'] != 'systemd':
            return False
        
        # TimeShift has good support for these families
        supported_families = ['debian', 'rhel', 'arch']
        return distro_info['family'] in supported_families
    
    def _get_service_management_info(self, distro_info: Dict[str, str]) -> Dict[str, str]:
        """Get service management information."""
        if distro_info['init_system'] == 'systemd':
            return {
                'system': 'systemd',
                'start_cmd': 'systemctl start',
                'stop_cmd': 'systemctl stop',
                'restart_cmd': 'systemctl restart',
                'reload_cmd': 'systemctl reload',
                'status_cmd': 'systemctl status',
                'enable_cmd': 'systemctl enable',
                'disable_cmd': 'systemctl disable'
            }
        elif distro_info['init_system'] == 'sysv':
            return {
                'system': 'sysv',
                'start_cmd': 'service',
                'stop_cmd': 'service',
                'restart_cmd': 'service',
                'reload_cmd': 'service',
                'status_cmd': 'service',
                'enable_cmd': 'chkconfig',
                'disable_cmd': 'chkconfig'
            }
        else:
            return {'system': 'unknown'}
    
    def _get_network_management_info(self, distro_info: Dict[str, str]) -> Dict[str, str]:
        """Get network management information."""
        if distro_info['family'] == 'debian':
            return {
                'primary': 'netplan',
                'legacy': 'interfaces',
                'manager': 'NetworkManager',
                'restart_cmd': 'systemctl restart networking'
            }
        elif distro_info['family'] == 'rhel':
            return {
                'primary': 'NetworkManager',
                'legacy': 'network',
                'manager': 'NetworkManager',
                'restart_cmd': 'systemctl restart NetworkManager'
            }
        else:
            return {
                'primary': 'unknown',
                'restart_cmd': 'systemctl restart networking'
            }
    
    def _get_firewall_management_info(self, distro_info: Dict[str, str]) -> Dict[str, str]:
        """Get firewall management information."""
        if distro_info['family'] == 'debian':
            return {
                'primary': 'ufw',
                'legacy': 'iptables',
                'enable_cmd': 'ufw --force enable',
                'disable_cmd': 'ufw --force disable',
                'reload_cmd': 'ufw reload'
            }
        elif distro_info['family'] == 'rhel':
            return {
                'primary': 'firewalld',
                'legacy': 'iptables',
                'enable_cmd': 'systemctl enable firewalld',
                'disable_cmd': 'systemctl disable firewalld',
                'reload_cmd': 'firewall-cmd --reload'
            }
        else:
            return {
                'primary': 'iptables',
                'reload_cmd': 'iptables-restore'
            }
    
    def _get_package_management_info(self, distro_info: Dict[str, str]) -> Dict[str, str]:
        """Get package management information."""
        pm = distro_info['package_manager']
        
        pm_info = {
            'apt': {
                'manager': 'apt',
                'install_cmd': 'apt install',
                'remove_cmd': 'apt remove',
                'update_cmd': 'apt update',
                'upgrade_cmd': 'apt upgrade',
                'search_cmd': 'apt search'
            },
            'yum': {
                'manager': 'yum',
                'install_cmd': 'yum install',
                'remove_cmd': 'yum remove',
                'update_cmd': 'yum update',
                'upgrade_cmd': 'yum upgrade',
                'search_cmd': 'yum search'
            },
            'dnf': {
                'manager': 'dnf',
                'install_cmd': 'dnf install',
                'remove_cmd': 'dnf remove',
                'update_cmd': 'dnf update',
                'upgrade_cmd': 'dnf upgrade',
                'search_cmd': 'dnf search'
            },
            'pacman': {
                'manager': 'pacman',
                'install_cmd': 'pacman -S',
                'remove_cmd': 'pacman -R',
                'update_cmd': 'pacman -Sy',
                'upgrade_cmd': 'pacman -Syu',
                'search_cmd': 'pacman -Ss'
            },
            'zypper': {
                'manager': 'zypper',
                'install_cmd': 'zypper install',
                'remove_cmd': 'zypper remove',
                'update_cmd': 'zypper refresh',
                'upgrade_cmd': 'zypper update',
                'search_cmd': 'zypper search'
            }
        }
        
        return pm_info.get(pm, {'manager': 'unknown'})
    
    def is_supported(self) -> bool:
        """Check if the current distribution is supported."""
        distro_info = self.detect()
        
        # We support most Linux distributions with systemd
        if distro_info['init_system'] == 'systemd':
            return True
        
        # Limited support for SysV init systems
        if distro_info['init_system'] == 'sysv':
            return True
        
        return False