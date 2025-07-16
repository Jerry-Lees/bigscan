#!/bin/bash

#######################################################################
# BIG-IP Device Information Extractor - Installation & Test Script
#######################################################################
#
# This script installs all dependencies and tests the BIG-IP scanner
# for new installations on Linux/macOS systems.
#
# Enhanced for improved QKView functionality with F5 autodeploy endpoints
#
# Usage:
#   chmod +x install.sh
#   ./install.sh
#
# Or with options:
#   ./install.sh --skip-system-deps    # Skip system package installation
#   ./install.sh --python-only         # Only install Python dependencies
#   ./install.sh --test-only           # Only run tests (skip installation)
#
#######################################################################

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script configuration
SCRIPT_NAME="bigscan.py"
VENV_NAME="bigip_scanner_env"
PYTHON_REQUIREMENTS="requests urllib3 certifi"

# Parse command line arguments
SKIP_SYSTEM_DEPS=false
PYTHON_ONLY=false
TEST_ONLY=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-system-deps)
            SKIP_SYSTEM_DEPS=true
            shift
            ;;
        --python-only)
            PYTHON_ONLY=true
            shift
            ;;
        --test-only)
            TEST_ONLY=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --skip-system-deps    Skip system package installation"
            echo "  --python-only         Only install Python dependencies"
            echo "  --test-only          Only run tests (skip installation)"
            echo "  -h, --help           Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

#######################################################################
# Helper Functions
#######################################################################

print_header() {
    echo -e "\n${BLUE}======================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        if command -v apt-get &> /dev/null; then
            echo "debian"
        elif command -v yum &> /dev/null; then
            echo "redhat"
        elif command -v dnf &> /dev/null; then
            echo "fedora"
        elif command -v pacman &> /dev/null; then
            echo "arch"
        else
            echo "linux"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "unknown"
    fi
}

check_command() {
    if command -v "$1" &> /dev/null; then
        return 0
    else
        return 1
    fi
}

install_python() {
    local os_type=$1
    
    print_info "Installing Python 3..."
    
    case $os_type in
        "debian")
            sudo apt-get update
            sudo apt-get install -y python3 python3-pip python3-venv python3-dev
            ;;
        "redhat")
            sudo yum install -y python3 python3-pip python3-devel
            ;;
        "fedora")
            sudo dnf install -y python3 python3-pip python3-devel
            ;;
        "arch")
            sudo pacman -S --noconfirm python python-pip
            ;;
        "macos")
            if check_command brew; then
                brew install python3
            else
                print_error "Homebrew not found. Please install Python 3 manually from https://python.org"
                exit 1
            fi
            ;;
        *)
            print_error "Unsupported OS. Please install Python 3 manually."
            exit 1
            ;;
    esac
}

#######################################################################
# Main Installation Functions
#######################################################################

check_prerequisites() {
    print_header "Checking Prerequisites"
    
    local os_type=$(detect_os)
    print_info "Detected OS: $os_type"
    
    # Check for Python 3
    if check_command python3; then
        local python_version=$(python3 --version 2>&1 | cut -d' ' -f2)
        print_success "Python 3 found: $python_version"
        
        # Check if Python version is 3.7 or higher (required for enhanced features)
        local major_version=$(echo $python_version | cut -d'.' -f1)
        local minor_version=$(echo $python_version | cut -d'.' -f2)
        
        if [[ $major_version -eq 3 && $minor_version -ge 7 ]] || [[ $major_version -gt 3 ]]; then
            print_success "Python version is compatible (3.7+)"
        else
            print_warning "Python version $python_version detected. Python 3.7+ recommended for best compatibility."
        fi
    else
        print_warning "Python 3 not found"
        if [[ "$SKIP_SYSTEM_DEPS" == false && "$PYTHON_ONLY" == false && "$TEST_ONLY" == false ]]; then
            install_python "$os_type"
        else
            print_error "Python 3 is required but not installed"
            exit 1
        fi
    fi
    
    # Check for pip
    if check_command pip3; then
        print_success "pip3 found"
    elif check_command pip; then
        print_success "pip found"
    else
        print_error "pip not found. Please install pip."
        exit 1
    fi
    
    # Check if script exists
    if [[ -f "$SCRIPT_NAME" ]]; then
        print_success "BIG-IP scanner script found: $SCRIPT_NAME"
    else
        print_error "BIG-IP scanner script not found: $SCRIPT_NAME"
        print_info "Please ensure $SCRIPT_NAME is in the current directory"
        exit 1
    fi
}

setup_virtual_environment() {
    print_header "Setting Up Virtual Environment"
    
    # Create virtual environment if it doesn't exist
    if [[ ! -d "$VENV_NAME" ]]; then
        print_info "Creating virtual environment: $VENV_NAME"
        python3 -m venv "$VENV_NAME"
        print_success "Virtual environment created"
    else
        print_info "Virtual environment already exists: $VENV_NAME"
    fi
    
    # Activate virtual environment
    print_info "Activating virtual environment"
    source "$VENV_NAME/bin/activate"
    
    # Upgrade pip
    print_info "Upgrading pip"
    pip install --upgrade pip
    
    print_success "Virtual environment ready"
}

install_python_dependencies() {
    print_header "Installing Python Dependencies"
    
    print_info "Installing required packages for enhanced QKView functionality..."
    
    # Install each package with version checking
    for package in $PYTHON_REQUIREMENTS; do
        print_info "Installing $package..."
        
        # Install with specific handling for different packages
        case $package in
            "requests")
                pip install "requests>=2.25.0"
                print_success "$package installed (with SSL support)"
                ;;
            "urllib3")
                pip install "urllib3>=1.26.0"
                print_success "$package installed (with enhanced SSL handling)"
                ;;
            "certifi")
                pip install "certifi>=2021.1.1"
                print_success "$package installed (for SSL certificate validation)"
                ;;
            *)
                pip install "$package"
                print_success "$package installed"
                ;;
        esac
    done
    
    # Show installed packages
    print_info "Installed packages for BIG-IP scanner:"
    pip list | grep -E "(requests|urllib3|certifi)" || echo "  (Package listing not available)"
    
    # Check for additional useful packages
    print_info "Checking for optional enhancements..."
    
    # Install colorama for better cross-platform colored output (optional)
    if pip install colorama >/dev/null 2>&1; then
        print_success "colorama installed (enhanced terminal colors)"
    else
        print_warning "colorama not installed (colored output may vary by platform)"
    fi
}

create_test_files() {
    print_header "Creating Test Files"
    
    # Create test CSV file with enhanced format
    local test_csv="test_devices.csv"
    cat > "$test_csv" << EOF
# Test CSV file for BIG-IP scanner
# Enhanced format for QKView functionality
# Format: ip,username,password
# Note: Empty username/password fields will prompt for credentials
ip,username,password
# Example entries (replace with real devices for testing):
# 10.100.100.30,admin,password123
# 192.168.1.100,root,
# 172.16.1.50,,
# bigip-lab.example.com,admin,
EOF
    
    print_success "Created test CSV file: $test_csv"
    print_info "Edit $test_csv with real device information for testing"
    
    # Create enhanced test script
    local test_script="test_scanner.py"
    cat > "$test_script" << 'EOF'
#!/usr/bin/env python3
"""
Enhanced Test script for BIG-IP Device Information Extractor
Tests both basic functionality and enhanced QKView features
"""

import sys
import subprocess
import importlib.util
import os
import tempfile

def test_imports():
    """Test that all required modules can be imported"""
    print("Testing module imports...")
    
    required_modules = ['requests', 'urllib3', 'csv', 'json', 'argparse', 'getpass', 'time', 'datetime']
    optional_modules = ['certifi', 'colorama']
    
    success = True
    
    for module in required_modules:
        try:
            if module in ['csv', 'json', 'argparse', 'getpass', 'time', 'datetime']:
                # Standard library modules
                __import__(module)
            else:
                # Third-party modules
                importlib.import_module(module)
            print(f"  ✓ {module} (required)")
        except ImportError as e:
            print(f"  ✗ {module} (required): {e}")
            success = False
    
    for module in optional_modules:
        try:
            importlib.import_module(module)
            print(f"  ✓ {module} (optional)")
        except ImportError:
            print(f"  ⚠ {module} (optional): Not installed")
    
    return success

def test_script_syntax():
    """Test that the main script has valid syntax"""
    print("\nTesting script syntax...")
    
    try:
        with open('bigscan.py', 'r') as f:
            source_code = f.read()
        
        compile(source_code, 'bigscan.py', 'exec')
        print("  ✓ Script syntax is valid")
        return True
    except SyntaxError as e:
        print(f"  ✗ Syntax error: {e}")
        return False
    except FileNotFoundError:
        print("  ✗ bigscan.py not found")
        return False

def test_script_import():
    """Test that the script can be imported without errors"""
    print("\nTesting script import...")
    
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("bigscan", "bigscan.py")
        if spec is None:
            print("  ✗ Could not create module spec")
            return False
            
        module = importlib.util.module_from_spec(spec)
        
        # Try to execute the module (this will catch import-time errors)
        spec.loader.exec_module(module)
        print("  ✓ Script imports successfully")
        
        # Test if BigIPInfoExtractor class exists
        if hasattr(module, 'BigIPInfoExtractor'):
            print("  ✓ BigIPInfoExtractor class found")
        else:
            print("  ✗ BigIPInfoExtractor class not found")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Import error: {e}")
        return False

def test_help_command():
    """Test that the script shows help without errors"""
    print("\nTesting help command...")
    
    try:
        result = subprocess.run([sys.executable, 'bigscan.py', '--help'], 
                              capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            if 'BIG-IP Device Information Extractor' in result.stdout or 'usage:' in result.stdout.lower():
                print("  ✓ Help command works correctly")
                
                # Check for QKView options
                if '--qkview' in result.stdout:
                    print("  ✓ QKView options found in help")
                else:
                    print("  ⚠ QKView options not found in help")
                
                return True
            else:
                print(f"  ✗ Help output doesn't contain expected content")
                return False
        else:
            print(f"  ✗ Help command failed with return code {result.returncode}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"  ✗ Help command timed out after 10 seconds")
        return False
    except Exception as e:
        print(f"  ✗ Error running help command: {e}")
        return False

def test_qkview_directory_creation():
    """Test that QKView directory can be created"""
    print("\nTesting QKView directory functionality...")
    
    try:
        # Test directory creation
        test_dir = "test_qkviews"
        if not os.path.exists(test_dir):
            os.makedirs(test_dir)
            print(f"  ✓ QKView directory creation works")
            
            # Clean up
            os.rmdir(test_dir)
            print(f"  ✓ Directory cleanup successful")
        else:
            print(f"  ✓ Directory already exists (cleanup from previous test)")
            
        return True
        
    except Exception as e:
        print(f"  ✗ Error testing QKView directory: {e}")
        return False

def test_csv_functionality():
    """Test CSV reading functionality"""
    print("\nTesting CSV functionality...")
    
    try:
        # Create a temporary CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("ip,username,password\n")
            f.write("192.168.1.100,admin,password123\n")
            f.write("10.0.0.1,user,\n")
            temp_csv = f.name
        
        # Test if the script can read CSV (import the function)
        spec = importlib.util.spec_from_file_location("bigscan", "bigscan.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        if hasattr(module, 'read_devices_from_csv'):
            devices = module.read_devices_from_csv(temp_csv)
            if len(devices) == 2:
                print("  ✓ CSV reading functionality works")
                result = True
            else:
                print(f"  ✗ Expected 2 devices, got {len(devices)}")
                result = False
        else:
            print("  ✗ read_devices_from_csv function not found")
            result = False
        
        # Clean up
        os.unlink(temp_csv)
        return result
        
    except Exception as e:
        print(f"  ✗ Error testing CSV functionality: {e}")
        return False

def main():
    """Run all tests"""
    print("Enhanced BIG-IP Scanner Test Suite")
    print("=" * 50)
    
    tests = [
        test_imports,
        test_script_syntax,
        test_script_import,
        test_help_command,
        test_qkview_directory_creation,
        test_csv_functionality
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\nTest Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ All tests passed! The enhanced BIG-IP scanner is ready to use.")
        print("\nFeatures available:")
        print("  • Device information extraction")
        print("  • Enhanced QKView generation with F5 autodeploy endpoint")
        print("  • Bulk processing from CSV files")
        print("  • Interactive and automated modes")
        return 0
    else:
        print("✗ Some tests failed. Please check the installation.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
EOF
    
    chmod +x "$test_script"
    print_success "Created enhanced test script: $test_script"
}

run_tests() {
    print_header "Running Enhanced Tests"
    
    # Run the test script
    if [[ -f "test_scanner.py" ]]; then
        python test_scanner.py
        local test_result=$?
        
        if [[ $test_result -eq 0 ]]; then
            print_success "All tests passed!"
        else
            print_error "Some tests failed"
            return 1
        fi
    else
        print_warning "Test script not found, running basic tests..."
        
        # Basic test - check if script runs without error
        print_info "Testing script help command..."
        if python "$SCRIPT_NAME" --help > /dev/null 2>&1; then
            print_success "Script runs without syntax errors"
        else
            print_error "Script has syntax errors or missing dependencies"
            return 1
        fi
    fi
    
    return 0
}

show_usage_examples() {
    print_header "Usage Examples"
    
    cat << 'EOF'
The enhanced BIG-IP scanner is now ready to use! Here are some examples:

# Interactive mode
python bigscan.py

# With credentials
python bigscan.py --user admin

# Bulk processing from CSV
python bigscan.py --in test_devices.csv --out results.csv

# Enhanced QKView functionality using F5 autodeploy endpoint
python bigscan.py --in test_devices.csv --qkview --out results.csv

# QKView with custom timeout (20 minutes)
python bigscan.py --user admin --qkview --qkview-timeout 1200

# Complete example with QKView
python bigscan.py --user admin --pass mypassword --qkview --out devices.csv

# Using the virtual environment (if created)
source bigip_scanner_env/bin/activate
python bigscan.py --help

Enhanced Features:
• F5 autodeploy endpoint for reliable QKView generation
• Real-time progress monitoring with spinning indicators
• Automatic cleanup of remote QKView tasks
• Enhanced error handling and recovery
• Improved session management with token extension
EOF
    
    print_info "Edit test_devices.csv with real device information for testing"
    print_info "Remember to activate the virtual environment: source $VENV_NAME/bin/activate"
    print_info "QKView files will be saved to the 'qkviews' directory"
}

cleanup_on_error() {
    print_error "Installation failed!"
    print_info "You can try running with different options:"
    print_info "  --skip-system-deps  (skip system package installation)"
    print_info "  --python-only       (only install Python dependencies)"
    print_info "  --test-only         (only run tests)"
}

#######################################################################
# Main Execution
#######################################################################

main() {
    print_header "BIG-IP Device Information Extractor - Enhanced Setup"
    print_info "Enhanced for improved QKView functionality with F5 autodeploy endpoints"
    
    # Set up error handling
    trap cleanup_on_error ERR
    
    if [[ "$TEST_ONLY" != true ]]; then
        check_prerequisites
        
        if [[ "$PYTHON_ONLY" != true ]]; then
            setup_virtual_environment
        fi
        
        install_python_dependencies
        create_test_files
    fi
    
    run_tests
    
    if [[ $? -eq 0 ]]; then
        show_usage_examples
        print_success "Enhanced installation and testing completed successfully!"
        print_info "The scanner now includes improved QKView functionality with F5 autodeploy endpoints"
    else
        print_error "Testing failed. Please check the output above."
        exit 1
    fi
}

# Run main function
main "$@"
