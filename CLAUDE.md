# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MeshAdminRevertIt is a timed confirmation system for Linux configuration changes with automatic revert capabilities. It's designed for remote system administrators to prevent loss of access due to configuration errors.

## Development Commands

### Installation and Setup
```bash
# Install in development mode
pip3 install -e .

# Install system dependencies (Ubuntu/Debian)
sudo apt install python3-dev python3-pip build-essential rsync inotify-tools

# Install TimeShift (optional, for enhanced snapshots)
sudo apt install timeshift
```

### Running and Testing
```bash
# Test system compatibility
meshadmin-revertit test

# Run daemon in foreground (development)
sudo python3 -m meshadmin_revertit.daemon.main --config config/meshadmin-revertit.yaml --foreground

# Run CLI commands
meshadmin-revertit status
meshadmin-revertit snapshots list
```

### Service Management
```bash
# Install systemd service
sudo cp systemd/meshadmin-revertit.service /etc/systemd/system/
sudo systemctl daemon-reload

# Start/stop service
sudo systemctl start meshadmin-revertit
sudo systemctl stop meshadmin-revertit
sudo systemctl status meshadmin-revertit
```

### Installation Scripts
```bash
# Full system installation
sudo ./scripts/install.sh

# Uninstall
sudo ./scripts/uninstall.sh
```

## Architecture Overview

### Core Components
1. **MeshAdminDaemon** - Main service monitoring system changes
2. **ConfigurationMonitor** - Watches critical system files using filesystem events
3. **SnapshotManager** - Manages system snapshots (TimeShift + manual snapshots)
4. **TimeoutManager** - Handles timed confirmations and automatic reverts
5. **RevertEngine** - Performs automatic reversion of configuration changes
6. **DistroDetector** - Detects Linux distribution and provides compatibility
7. **CLI Interface** - Command-line management tools

### Key Files and Directories
- `src/meshadmin_revertit/` - Main Python package
- `config/meshadmin-revertit.yaml` - Default configuration file
- `systemd/meshadmin-revertit.service` - systemd service definition
- `scripts/install.sh` - Installation script
- `/etc/meshadmin-revertit/` - Runtime configuration directory
- `/var/lib/meshadmin-revertit/` - Runtime data and snapshots
- `/var/log/meshadmin-revertit.log` - Main log file

### Workflow
1. Daemon monitors critical configuration files
2. On change detection, creates snapshot and starts timeout
3. User must confirm change within timeout period
4. If not confirmed or connectivity lost, automatically reverts using snapshot
5. Supports different timeout periods per change category (network, SSH, firewall, etc.)

### Monitored Configuration Categories
- **Network**: `/etc/network/interfaces`, `/etc/netplan/*`, NetworkManager configs
- **SSH**: `/etc/ssh/sshd_config`, `/etc/ssh/ssh_config.d/*`
- **Firewall**: `/etc/iptables/*`, `/etc/ufw/*`, `/etc/firewalld/*`
- **Services**: `/etc/systemd/system/*`, `/etc/systemd/user/*`

## Configuration

Main config: `config/meshadmin-revertit.yaml` or `/etc/meshadmin-revertit/config.yaml`

Key sections:
- `global`: Basic daemon settings, timeouts, logging
- `snapshot`: TimeShift integration, snapshot storage
- `monitoring`: File paths to monitor per category
- `timeout`: Timeout behavior, connectivity checking
- `distro`: Distribution-specific overrides

## Testing and Development

The system requires root privileges for full functionality (monitoring system files, creating snapshots, restarting services).

For development:
1. Use `meshadmin-revertit test` to verify system compatibility
2. Run daemon in foreground mode for debugging
3. Test with non-critical configuration files first
4. Always have out-of-band access when testing network changes

## Security Notes

- Runs as root (required for system configuration management)
- Monitors sensitive system files
- Creates snapshots that may contain sensitive data
- No remote interfaces by default (local operation only)
- Automatic cleanup of old snapshots to prevent data accumulation