# BIG-IP Device Information Extractor

A comprehensive Python script for extracting detailed system information from F5 BIG-IP devices via REST API. This tool connects to BIG-IP devices and extracts hardware, software, licensing, and configuration information, exporting the data to CSV format for analysis and reporting.

## Features

- **Comprehensive Data Extraction**: Hostname, serial number, registration key, software version, hotfixes, platform info, and more
- **Enhanced QKView Generation**: Creates and downloads QKView diagnostic files using F5's official autodeploy endpoint
- **Real-time Progress Monitoring**: Live status updates with spinning progress indicators during QKView creation
- **Bulk Processing**: Process multiple devices from CSV input file
- **Flexible Authentication**: Command line credentials, interactive prompts, or CSV-based authentication
- **Token-Based Authentication**: Uses BIG-IP REST API with secure token authentication and automatic timeout extension
- **CSV Export**: Structured output for easy analysis and reporting
- **Automatic Cleanup**: Removes temporary files and tasks from BIG-IP devices after processing
- **Cross-Platform**: Works on Linux, macOS, and Windows

## License

This project is provided as-is for educational and administrative purposes. Please ensure compliance with your organization's security policies when using this tool.

## Disclaimer

This script is designed to assist in information gathering from F5 BIG-IP devices and has been tested in various environments. However, it may not work properly in all use cases or configurations. The script is provided "as is" without any warranty of merchantability, fitness for a particular purpose, or guarantee of functionality. Users should thoroughly test the script in a non-production environment to ensure proper operation within their specific environment before deploying in production systems. The authors and contributors assume no responsibility for any issues, damages, or operational impacts that may result from the use of this script.

## Getting Started

### Quick Setup (Recommended)

For new systems, use the automated installation script:

```bash
# Clone the repository
git clone https://github.com/Jerry-Lees/bigscan.git
cd bigscan

# Make the installer executable
chmod +x install.sh

# Run full installation and testing
./install.sh

# Activate the virtual environment (if created)
source bigip_scanner_env/bin/activate

# Test the installation
python bigscan.py --help
```

### First Run Examples

```bash
# Interactive mode - easiest for beginners
python bigscan.py

# Single device with credentials
python bigscan.py --user admin

# Include QKView generation
python bigscan.py --user admin --qkview

# Bulk processing from CSV file
python bigscan.py --in test_devices.csv --out results.csv
```

## Files Overview

### Core Files

| File | Description | Purpose |
|------|-------------|---------|
| `bigscan.py` | Main scanner script | Extracts device information and creates QKViews |
| `install.sh` | Installation and test script | Sets up dependencies and validates installation |
| `README.md` | Documentation | This file - complete usage guide |

### Generated Files (Created by Scripts)

| File | Description | Created By |
|------|-------------|------------|
| `bigip_device_info.csv` | Default output file | `bigscan.py` (default output) |
| `test_devices.csv` | Sample input CSV template | `install.sh` |
| `test_scanner.py` | Automated test suite | `install.sh` |
| `bigip_scanner_env/` | Python virtual environment | `install.sh` |
| `qkviews/` | QKView download directory | `bigscan.py` (when using --qkview) |

## Installation

### Automated Installation

The `install.sh` script handles all dependencies and setup:

```bash
# Full installation with testing
./install.sh

# Installation options
./install.sh --skip-system-deps    # Skip system package installation
./install.sh --python-only         # Only install Python dependencies  
./install.sh --test-only           # Only run tests (skip installation)
./install.sh --help               # Show installation help
```

### Manual Installation

```bash
# Install Python dependencies
pip install requests urllib3 certifi

# Or using virtual environment (recommended)
python3 -m venv bigip_scanner_env
source bigip_scanner_env/bin/activate
pip install requests urllib3 certifi
```

### Installation Script Options

| Option | Description | Use Case |
|--------|-------------|----------|
| `--skip-system-deps` | Skip system package installation | Restricted environments, containers |
| `--python-only` | Only install Python dependencies | When Python is already installed |
| `--test-only` | Only run tests (skip installation) | Verify existing installation |
| `--help` | Show installation help | Get detailed usage information |

## Usage

### Basic Usage

```bash
# Interactive mode - prompts for device details
python bigscan.py

# With username (will prompt for password)
python bigscan.py --user admin

# Complete example with credentials
python bigscan.py --user admin --pass mypassword --out results.csv
```

### QKView Generation

The script can create and download QKView diagnostic files using F5's official autodeploy endpoint:

```bash
# Single device with QKView
python bigscan.py --user admin --qkview

# Bulk processing with QKView generation
python bigscan.py --in devices.csv --qkview --out results.csv

# QKView with custom timeout (20 minutes)
python bigscan.py --user admin --qkview --qkview-timeout 1200
```

### Bulk Processing

```bash
# Process multiple devices from CSV
python bigscan.py --in devices.csv --out results.csv

# With fallback credentials for devices without CSV credentials
python bigscan.py --in devices.csv --user admin --out audit_results.csv

# Complete bulk processing with QKView
python bigscan.py --in devices.csv --user admin --qkview --out full_audit.csv
```

## Command Line Options

### Main Script (`bigscan.py`)

| Option | Short | Description | Example |
|--------|-------|-------------|---------|
| `--user` | `-u` | Username for authentication | `--user admin` |
| `--pass` | `-p` | Password for authentication | `--pass mypassword` |
| `--out` | `-o` | Output CSV filename | `--out devices.csv` |
| `--in` | `-i` | Input CSV filename | `--in device_list.csv` |
| `--qkview` | `-q` | Create and download QKView files | `--qkview` |
| `--qkview-timeout` | | QKView creation timeout (seconds) | `--qkview-timeout 1200` |
| `--no-qkview` | | Explicitly disable QKView creation | `--no-qkview` |
| `--help` | `-h` | Show help message | `--help` |

**Security Note**: Using `--pass` in command line is not recommended as passwords may be visible in process lists and command history.

### Installation Script (`install.sh`)

| Option | Description | Use Case |
|--------|-------------|----------|
| `--skip-system-deps` | Skip system package installation | Docker containers, restricted environments |
| `--python-only` | Only install Python dependencies | When system packages are already installed |
| `--test-only` | Only run tests (skip installation) | Verify existing installation |
| `--help` | Show installation help | Get detailed installation options |

## Input CSV Format

Create a CSV file with device information for bulk processing:

```csv
ip,username,password
10.100.100.30,admin,mypassword
10.100.100.31,root,
192.168.1.100,,
172.16.1.50,user1,pass123
bigip-lab.example.com,admin,
```

### CSV Format Rules

- **IP Address** (required): First column, BIG-IP device IP or hostname
- **Username** (optional): Second column, leave empty to use command line `--user` or prompt
- **Password** (optional): Third column, leave empty to use command line `--pass` or prompt
- **Headers**: Optional, script auto-detects headers
- **Empty rows**: Automatically skipped

**Security Note**: Including passwords in CSV files is not recommended for security reasons, though it may be necessary for automation or convenience. If you do store passwords in CSV files, ensure they are properly secured with restrictive file permissions (e.g., `chmod 600 devices.csv`), stored in secure locations, and access is limited to authorized personnel only.

### Credential Priority

1. **CSV file credentials** (if provided and not empty)
2. **Command line arguments** (`--user`, `--pass`)
3. **Interactive prompts** (if both above are missing)

## Output Format

The script generates a CSV file with the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| `management_ip` | Device IP address | `10.100.100.30` |
| `hostname` | Device hostname | `BIGIP-01.company.com` |
| `serial_number` | Chassis serial number | `dfac18d2-466d-fc43-5cb74c9d3b49` |
| `registration_key` | F5 registration key | `ABCDE-FGHIJ-KLMNO-PQRST-UVWXYZ` |
| `platform` | Hardware platform | `Z100` |
| `active_version` | Current TMOS version | `17.1.2` |
| `available_versions` | All boot locations | `HD1.1 (17.1.2); HD1.2 (16.1.4)` |
| `installed_hotfixes` | Installed hotfixes | `Hotfix-BIG-17.1.2-0.0.50` |
| `emergency_hotfixes` | Emergency hotfixes | `None` |
| `system_time` | Current system time | `2025-07-14 15:30:45` |
| `total_memory` | Total system memory | `8.0GB` |
| `memory_used` | Used system memory | `4.2GB` |
| `tmm_memory` | TMM memory usage | `2.1GB` |
| `cpu_count` | Number of CPUs | `4` |
| `ha_status` | High availability status | `Standalone` |
| `qkview_downloaded` | QKView download status | `Yes` / `Failed` / `Not requested` |
| `extraction_timestamp` | When data was collected | `2025-07-14 15:30:45` |

## QKView Functionality

### What is QKView?
QKView is F5's diagnostic file format that contains comprehensive system information for troubleshooting. The script uses F5's official autodeploy endpoint for reliable QKView generation.

### QKView Features
- **F5 Autodeploy Endpoint**: Uses the official `/mgmt/cm/autodeploy/qkview` endpoint
- **Asynchronous Processing**: Monitors task completion with real-time progress
- **Automatic Download**: Downloads completed QKViews to local `qkviews/` directory
- **Cleanup**: Automatically removes temporary files from BIG-IP devices
- **Progress Indicators**: Shows spinning progress and countdown timers
- **Error Handling**: Comprehensive error handling and recovery

### QKView File Naming
QKView files are named using the format: `{hostname}_{timestamp}.qkview`
- Example: `bigip-01.example.com_20250714_153045.qkview`

### QKView Timeout
- **Default**: 1200 seconds (20 minutes)
- **Configurable**: Use `--qkview-timeout` to adjust
- **Recommendation**: 900-1800 seconds depending on system size

## Examples

### Getting Started Examples

```bash
# First time setup
./install.sh
source bigip_scanner_env/bin/activate

# Interactive mode for single device
python bigscan.py

# Single device with QKView
python bigscan.py --user admin --qkview
```

### Production Examples

```bash
# Weekly audit with timestamp
python bigscan.py --in production_devices.csv --out audit_$(date +%Y%m%d).csv

# Department-specific scan with QKView
python bigscan.py --in datacenter_devices.csv --user audit_account --qkview --out datacenter_audit.csv

# Emergency hotfix check
python bigscan.py --in critical_devices.csv --out hotfix_status.csv

# Complete audit with QKView and extended timeout
python bigscan.py --in all_devices.csv --qkview --qkview-timeout 1800 --out complete_audit.csv
```

### Bulk Processing Examples

```bash
# Create input file
cat > devices.csv << EOF
ip,username,password
10.100.100.30,admin,secret123
10.100.100.31,root,
192.168.1.100,,
bigip-lab.example.com,admin,
EOF

# Process all devices
python bigscan.py --in devices.csv --user fallback_admin --out results.csv

# With QKView generation
python bigscan.py --in devices.csv --user fallback_admin --qkview --out results.csv
```

## Troubleshooting

### Common Issues

#### Installation Problems
```bash
# Check Python version (3.7+ required)
python3 --version

# Reinstall dependencies
./install.sh --python-only

# Test installation
./install.sh --test-only
```

#### Authentication Failures
```bash
# Test authentication manually
python bigscan.py --user admin
# Enter device IP when prompted

# Check credentials
python bigscan.py --user admin --pass mypassword
```

#### QKView Issues
```bash
# Check QKView directory permissions
ls -la qkviews/

# Increase QKView timeout
python bigscan.py --user admin --qkview --qkview-timeout 1800

# Check available disk space
df -h
```

#### Network/API Issues
```bash
# Test basic connectivity
curl -k https://your-bigip-ip/mgmt/tm/sys/version

# Check firewall rules (port 443 required)
telnet your-bigip-ip 443
```

### Error Messages

| Error | Cause | Solution |
|-------|--------|----------|
| `401 Unauthorized` | Invalid credentials | Check username/password |
| `Connection refused` | Network/firewall issue | Verify IP and network connectivity |
| `QKView creation timed out` | QKView taking too long | Increase timeout with `--qkview-timeout` |
| `Module not found` | Missing dependencies | Run `./install.sh --python-only` |
| `File not found` | Missing input CSV | Check file path and permissions |
| `Permission denied` | Insufficient permissions | Check file/directory permissions |

### Debug Information

The script provides detailed progress information:
- Authentication status
- API call results
- QKView creation progress
- Download status
- Cleanup operations

## System Requirements

### Supported Platforms
- **Linux**: Ubuntu, RHEL, CentOS, Fedora, Arch Linux
- **macOS**: 10.14+ with Homebrew
- **Windows**: Windows 10+ with Python 3.7+

### Dependencies
- **Python**: 3.7 or higher (3.8+ recommended)
- **Python Packages**: 
  - `requests>=2.25.0` (HTTP client for REST API)
  - `urllib3>=1.26.0` (Enhanced HTTP library)
  - `certifi>=2021.1.1` (SSL certificate validation)
- **System Packages**: 
  - `python3-pip` (package installer)
  - `python3-venv` (virtual environment support)
  - `python3-dev` (development headers for native extensions)

### F5 BIG-IP Compatibility
- **TMOS**: 12.0+ (tested extensively on 16.x, 17.x)
- **Access**: Management interface access required
- **Permissions**: Read-only access sufficient for device info, admin required for QKView
- **Protocols**: HTTPS (port 443)
- **QKView**: Autodeploy endpoint available in TMOS 13.0+

## Security Considerations

### Authentication Security
- **Token-based**: Uses F5's secure token authentication with automatic timeout extension
- **Session Management**: Proper session cleanup and logout procedures
- **Password Handling**: Passwords never stored, only used for token generation
- **Command Line**: Avoid `--pass` in production scripts
- **CSV Storage**: Secure CSV files containing credentials appropriately

### Network Security
- **HTTPS Only**: All communications encrypted
- **Certificate Validation**: Disabled for self-signed certificates (common with BIG-IP)
- **Firewall**: Ensure port 443 access to BIG-IP management interface
- **Token Timeout**: Automatic token extension for long-running operations

### Best Practices
1. Use service accounts with minimal required permissions
2. Store credential CSV files securely with restricted permissions (chmod 600)
3. Use virtual environments to isolate dependencies
4. Regularly rotate service account credentials
5. Audit script usage and output file access
6. Use QKView functionality only when needed (admin permissions required)
7. Monitor QKView file storage and cleanup

## Development

### Contributing
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `./install.sh --test-only`
5. Submit a pull request

### Testing
```bash
# Run all tests
./install.sh --test-only

# Manual testing
python test_scanner.py

# Test specific functionality
python bigscan.py --help

# Test QKView functionality
python bigscan.py --user admin --qkview
```

### Code Structure
The script is modular and can be extended:
- **BigIPInfoExtractor class**: Core device information extraction
- **QKView methods**: Enhanced QKView functionality using F5 autodeploy endpoint
- **CSV handling**: Input/output CSV processing
- **Authentication**: Token-based authentication with session management
- **Progress reporting**: Real-time status updates with visual indicators

## Performance Considerations

### QKView Generation
- **Time**: 5-15 minutes per device depending on configuration complexity
- **Storage**: QKView files typically 50-500MB each
- **Memory**: Minimal memory usage with streaming downloads
- **Concurrent**: Process devices sequentially to avoid overwhelming BIG-IP

### Bulk Processing
- **Scaling**: Can handle hundreds of devices with proper timeout settings
- **Rate Limiting**: Built-in delays prevent API overload
- **Error Handling**: Continues processing remaining devices on individual failures
- **Progress Tracking**: Real-time progress indicators for long operations

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Run the installation test script: `./install.sh --test-only`
3. Use interactive mode for debugging: `python bigscan.py`
4. Check F5 documentation for REST API changes
5. Verify network connectivity and permissions

## Changelog

### Version 2.0 (Current)
- Enhanced QKView functionality using F5 autodeploy endpoint
- Real-time progress monitoring with spinning indicators
- Improved error handling and recovery
- Better session management with token timeout extension
- Automatic cleanup of remote files and tasks
- Enhanced installation script with better dependency management

### Version 1.0 (Legacy)
- Basic device information extraction
- CSV input/output functionality
- Token-based authentication
- Cross-platform compatibility

---

**Last Updated**: July 2025  
**Version**: 2.0  
**Tested with**: TMOS 16.1.x, 17.1.x, Python 3.7-3.12

