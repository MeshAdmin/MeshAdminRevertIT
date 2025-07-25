#!/bin/bash
set -e

# MeshAdminRevertIt Uninstallation Script

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
CONFIG_DIR="/etc/meshadmin-revertit"
LOG_DIR="/var/log"
DATA_DIR="/var/lib/meshadmin-revertit"
SYSTEMD_DIR="/etc/systemd/system"

# Print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}Error: This script must be run as root${NC}"
        echo "Please run: sudo $0"
        exit 1
    fi
}

# Stop and disable service
stop_service() {
    print_status "Stopping MeshAdminRevertIt service..."
    
    if systemctl is-active --quiet meshadmin-revertit; then
        systemctl stop meshadmin-revertit
        print_success "Service stopped"
    fi
    
    if systemctl is-enabled --quiet meshadmin-revertit 2>/dev/null; then
        systemctl disable meshadmin-revertit
        print_success "Service disabled"
    fi
}

# Remove systemd service
remove_systemd_service() {
    print_status "Removing systemd service..."
    
    if [[ -f "$SYSTEMD_DIR/meshadmin-revertit.service" ]]; then
        rm -f "$SYSTEMD_DIR/meshadmin-revertit.service"
        systemctl daemon-reload
        print_success "systemd service removed"
    else
        print_status "systemd service file not found"
    fi
}

# Uninstall Python package
uninstall_package() {
    print_status "Uninstalling Python package..."
    
    if pip3 show meshadmin-revertit &>/dev/null; then
        pip3 uninstall -y meshadmin-revertit
        print_success "Python package uninstalled"
    else
        print_status "Python package not found"
    fi
}

# Remove files and directories
remove_files() {
    print_status "Removing files and directories..."
    
    # Ask about configuration and data
    echo
    echo -e "${YELLOW}The following directories contain configuration and data:${NC}"
    echo "  Configuration: $CONFIG_DIR"
    echo "  Data/Snapshots: $DATA_DIR"
    echo "  Logs: $LOG_DIR/meshadmin-revertit.log*"
    echo
    
    read -p "Remove configuration files? (y/N): " remove_config
    if [[ "$remove_config" =~ ^[Yy]$ ]]; then
        if [[ -d "$CONFIG_DIR" ]]; then
            rm -rf "$CONFIG_DIR"
            print_success "Configuration directory removed"
        fi
    else
        print_status "Configuration files preserved"
    fi
    
    read -p "Remove data directory and snapshots? (y/N): " remove_data
    if [[ "$remove_data" =~ ^[Yy]$ ]]; then
        if [[ -d "$DATA_DIR" ]]; then
            rm -rf "$DATA_DIR"
            print_success "Data directory removed"
        fi
    else
        print_status "Data directory preserved"
    fi
    
    read -p "Remove log files? (y/N): " remove_logs
    if [[ "$remove_logs" =~ ^[Yy]$ ]]; then
        rm -f "$LOG_DIR"/meshadmin-revertit.log*
        print_success "Log files removed"
    else
        print_status "Log files preserved"
    fi
    
    # Remove logrotate configuration
    if [[ -f /etc/logrotate.d/meshadmin-revertit ]]; then
        rm -f /etc/logrotate.d/meshadmin-revertit
        print_success "Log rotation configuration removed"
    fi
}

# Clean up any remaining processes
cleanup_processes() {
    print_status "Cleaning up any remaining processes..."
    
    # Check for running daemon
    if pgrep -f meshadmin-daemon &>/dev/null; then
        print_warning "Found running daemon processes"
        pkill -f meshadmin-daemon || true
        sleep 2
        
        # Force kill if still running
        if pgrep -f meshadmin-daemon &>/dev/null; then
            pkill -9 -f meshadmin-daemon || true
            print_success "Forced termination of daemon processes"
        else
            print_success "Daemon processes terminated"
        fi
    else
        print_status "No running daemon processes found"
    fi
    
    # Remove PID file if exists
    if [[ -f /var/run/meshadmin-revertit.pid ]]; then
        rm -f /var/run/meshadmin-revertit.pid
        print_success "PID file removed"
    fi
}

# Verify uninstallation
verify_uninstall() {
    print_status "Verifying uninstallation..."
    
    # Check if commands are still available
    if command -v meshadmin-revertit &>/dev/null; then
        print_warning "meshadmin-revertit command still available"
        return 1
    fi
    
    if command -v meshadmin-daemon &>/dev/null; then
        print_warning "meshadmin-daemon command still available"
        return 1
    fi
    
    # Check if service is still installed
    if [[ -f "$SYSTEMD_DIR/meshadmin-revertit.service" ]]; then
        print_warning "systemd service file still exists"
        return 1
    fi
    
    print_success "Uninstallation verification passed"
    return 0
}

# Main uninstallation function
main() {
    echo -e "${BLUE}MeshAdminRevertIt Uninstallation Script${NC}"
    echo "========================================"
    echo
    
    print_warning "This will remove MeshAdminRevertIt from your system."
    echo
    read -p "Are you sure you want to continue? (y/N): " confirm
    
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_status "Uninstallation cancelled"
        exit 0
    fi
    
    echo
    check_root
    stop_service
    remove_systemd_service
    cleanup_processes
    uninstall_package
    remove_files
    
    if verify_uninstall; then
        echo
        print_success "MeshAdminRevertIt has been successfully uninstalled!"
        echo
        print_status "Thank you for using MeshAdminRevertIt."
    else
        echo
        print_warning "Uninstallation completed with warnings."
        print_status "Some files or commands may still be present."
        echo
    fi
}

# Run main function
main