#!/bin/bash
set -e

# MeshAdminRevertIt Installation Script
# This script installs MeshAdminRevertIt on Ubuntu Linux and compatible distributions

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
INSTALL_PREFIX="/usr/local"
CONFIG_DIR="/etc/meshadmin-revertit"
LOG_DIR="/var/log"
DATA_DIR="/var/lib/meshadmin-revertit"
SYSTEMD_DIR="/etc/systemd/system"

# Check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}Error: This script must be run as root${NC}"
        echo "Please run: sudo $0"
        exit 1
    fi
}

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

# Detect distribution
detect_distro() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        DISTRO_ID="$ID"
        DISTRO_NAME="$NAME"
        DISTRO_VERSION="$VERSION_ID"
    else
        print_error "Cannot detect Linux distribution"
        exit 1
    fi
    
    print_status "Detected distribution: $DISTRO_NAME $DISTRO_VERSION"
}

# Check system requirements
check_requirements() {
    print_status "Checking system requirements..."
    
    # Check Python version
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is required but not installed"
        exit 1
    fi
    
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)
    if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)"; then
        print_error "Python 3.8 or higher is required (found $PYTHON_VERSION)"
        exit 1
    fi
    
    print_success "Python version: $PYTHON_VERSION"
    
    # Check pip
    if ! command -v pip3 &> /dev/null; then
        print_warning "pip3 not found, installing..."
        case "$DISTRO_ID" in
            ubuntu|debian)
                apt-get update
                apt-get install -y python3-pip
                ;;
            centos|rhel|fedora)
                if command -v dnf &> /dev/null; then
                    dnf install -y python3-pip
                else
                    yum install -y python3-pip
                fi
                ;;
            *)
                print_error "Please install pip3 manually for your distribution"
                exit 1
                ;;
        esac
    fi
    
    # Check systemd
    if ! systemctl --version &> /dev/null; then
        print_warning "systemd not detected - service management may be limited"
    else
        print_success "systemd detected"
    fi
    
    # Check TimeShift (optional)
    if command -v timeshift &> /dev/null; then
        print_success "TimeShift found - enhanced snapshot capabilities available"
    else
        print_warning "TimeShift not found - manual snapshots will be used"
        print_status "To install TimeShift: apt install timeshift (Ubuntu/Debian)"
    fi
}

# Install system dependencies
install_dependencies() {
    print_status "Installing system dependencies..."
    
    case "$DISTRO_ID" in
        ubuntu|debian)
            apt-get update
            apt-get install -y \
                python3-dev \
                python3-pip \
                python3-setuptools \
                python3-wheel \
                build-essential \
                rsync \
                inotify-tools
            ;;
        centos|rhel|fedora)
            if command -v dnf &> /dev/null; then
                dnf install -y \
                    python3-devel \
                    python3-pip \
                    python3-setuptools \
                    python3-wheel \
                    gcc \
                    rsync \
                    inotify-tools
            else
                yum install -y \
                    python3-devel \
                    python3-pip \
                    python3-setuptools \
                    python3-wheel \
                    gcc \
                    rsync \
                    inotify-tools
            fi
            ;;
        arch)
            pacman -Sy --noconfirm \
                python \
                python-pip \
                python-setuptools \
                python-wheel \
                base-devel \
                rsync \
                inotify-tools
            ;;
        *)
            print_warning "Unknown distribution - you may need to install dependencies manually"
            ;;
    esac
    
    print_success "System dependencies installed"
}

# Create directories
create_directories() {
    print_status "Creating directories..."
    
    mkdir -p "$CONFIG_DIR"
    mkdir -p "$DATA_DIR/snapshots"
    mkdir -p "$LOG_DIR"
    
    # Set permissions
    chmod 755 "$CONFIG_DIR"
    chmod 755 "$DATA_DIR"
    chmod 700 "$DATA_DIR/snapshots"
    
    print_success "Directories created"
}

# Install Python package
install_package() {
    print_status "Installing MeshAdminRevertIt Python package..."
    
    cd "$PROJECT_DIR"
    
    # Install in development mode or from source
    if [[ -f setup.py ]]; then
        pip3 install -e .
    else
        print_error "setup.py not found in $PROJECT_DIR"
        exit 1
    fi
    
    print_success "Python package installed"
}

# Install configuration
install_configuration() {
    print_status "Installing configuration..."
    
    # Copy default configuration if it doesn't exist
    if [[ ! -f "$CONFIG_DIR/config.yaml" ]]; then
        cp "$PROJECT_DIR/config/meshadmin-revertit.yaml" "$CONFIG_DIR/config.yaml"
        print_success "Default configuration installed"
    else
        print_warning "Configuration file already exists - not overwriting"
        
        # Create backup of new config
        cp "$PROJECT_DIR/config/meshadmin-revertit.yaml" "$CONFIG_DIR/config.yaml.new"
        print_status "New configuration saved as config.yaml.new"
    fi
    
    # Set permissions
    chmod 644 "$CONFIG_DIR/config.yaml"
    chown root:root "$CONFIG_DIR/config.yaml"
}

# Install systemd service
install_systemd_service() {
    print_status "Installing systemd service..."
    
    if [[ ! -d "$SYSTEMD_DIR" ]]; then
        print_warning "systemd not available - skipping service installation"
        return
    fi
    
    # Copy service file
    cp "$PROJECT_DIR/systemd/meshadmin-revertit.service" "$SYSTEMD_DIR/"
    
    # Set permissions
    chmod 644 "$SYSTEMD_DIR/meshadmin-revertit.service"
    chown root:root "$SYSTEMD_DIR/meshadmin-revertit.service"
    
    # Reload systemd
    systemctl daemon-reload
    
    print_success "systemd service installed"
    print_status "To enable at boot: systemctl enable meshadmin-revertit"
    print_status "To start now: systemctl start meshadmin-revertit"
}

# Create log rotation configuration
setup_log_rotation() {
    print_status "Setting up log rotation..."
    
    cat > /etc/logrotate.d/meshadmin-revertit << EOF
/var/log/meshadmin-revertit.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 644 root root
    postrotate
        systemctl reload meshadmin-revertit || true
    endscript
}
EOF
    
    print_success "Log rotation configured"
}

# Verify installation
verify_installation() {
    print_status "Verifying installation..."
    
    # Check if commands are available
    if command -v meshadmin-revertit &> /dev/null; then
        print_success "meshadmin-revertit command available"
    else
        print_error "meshadmin-revertit command not found"
        return 1
    fi
    
    if command -v meshadmin-daemon &> /dev/null; then
        print_success "meshadmin-daemon command available"
    else
        print_error "meshadmin-daemon command not found"
        return 1
    fi
    
    # Test basic functionality
    print_status "Testing basic functionality..."
    
    if meshadmin-revertit test; then
        print_success "Basic functionality test passed"
    else
        print_warning "Basic functionality test failed - check configuration"
    fi
    
    return 0
}

# Print post-installation instructions
print_post_install() {
    echo
    print_success "MeshAdminRevertIt installation completed!"
    echo
    echo -e "${BLUE}Next steps:${NC}"
    echo "1. Review configuration: $CONFIG_DIR/config.yaml"
    echo "2. Enable service: systemctl enable meshadmin-revertit"
    echo "3. Start service: systemctl start meshadmin-revertit"
    echo "4. Check status: meshadmin-revertit status"
    echo "5. Run system test: meshadmin-revertit test"
    echo
    echo -e "${BLUE}Usage examples:${NC}"
    echo "  meshadmin-revertit status          # Show system status"
    echo "  meshadmin-revertit snapshots list  # List snapshots"
    echo "  meshadmin-revertit confirm <id>    # Confirm a change"
    echo
    echo -e "${BLUE}Documentation:${NC}"
    echo "  Configuration: $CONFIG_DIR/config.yaml"
    echo "  Log file: /var/log/meshadmin-revertit.log"
    echo "  Data directory: $DATA_DIR"
    echo
    if [[ ! -f /usr/bin/timeshift ]]; then
        echo -e "${YELLOW}Optional:${NC} Install TimeShift for enhanced snapshot capabilities:"
        case "$DISTRO_ID" in
            ubuntu|debian)
                echo "  apt install timeshift"
                ;;
            centos|rhel|fedora)
                echo "  # TimeShift may need to be compiled from source"
                ;;
        esac
        echo
    fi
}

# Main installation function
main() {
    echo -e "${BLUE}MeshAdminRevertIt Installation Script${NC}"
    echo "======================================"
    echo
    
    check_root
    detect_distro
    check_requirements
    install_dependencies
    create_directories
    install_package
    install_configuration
    install_systemd_service
    setup_log_rotation
    
    if verify_installation; then
        print_post_install
    else
        print_error "Installation verification failed"
        exit 1
    fi
}

# Handle command line arguments
case "${1:-}" in
    --help|-h)
        echo "MeshAdminRevertIt Installation Script"
        echo
        echo "Usage: $0 [options]"
        echo
        echo "Options:"
        echo "  --help, -h     Show this help message"
        echo "  --uninstall    Uninstall MeshAdminRevertIt"
        echo
        exit 0
        ;;
    --uninstall)
        source "$SCRIPT_DIR/uninstall.sh"
        exit $?
        ;;
    *)
        main
        ;;
esac