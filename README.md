# BIG-IP Device Information Extractor

A comprehensive Python script for extracting detailed system information from F5 BIG-IP devices via REST API. This tool connects to BIG-IP devices and extracts hardware, software, licensing, and configuration information, exporting the data to CSV format for analysis and reporting.

## Features

- **Comprehensive Data Extraction**: Hostname, serial number, registration key, software version, hotfixes, platform info, and more
- **Bulk Processing**: Process multiple devices from CSV input file
- **Flexible Authentication**: Command line credentials, interactive prompts, or CSV-based authentication
- **Token-Based Authentication**: Uses BIG-IP REST API with secure token authentication
- **CSV Export**: Structured output for easy analysis and reporting
- **Debug Modes**: Built-in debugging tools for troubleshooting API issues
- **Cross-Platform**: Works on Linux, macOS, and Windows

## Files Overview

### Core Files

| File | Description | Purpose |
|------|-------------|---------|
| `bigscan.py` | Main scanner script | Extracts device information from BIG-IP devices |
| `install.sh` | Installation and test script | Sets up dependencies and validates installation |
| `README.md` | Documentation | This file - complete usage guide |

### Generated Files (Created by Scripts)

| File | Description | Created By |
|------|-------------|------------|
| `bigip_device_info.csv` | Default output file | `bigscan.py` (default output) |
| `test_devices.csv` | Sample input CSV template | `install.sh` |
| `test_scanner.py` | Automated test suite | `install.sh` |
| `bigip_scanner_env/` | Python virtual environment | `install.sh` |

## Installation

### Quick Setup (Recommended)

```bash
# Make the installer executable
chmod +x install.sh

# Run full installation and testing
./install.sh
```

### Manual Installation

```bash
# Install Python dependencies
pip install requests urllib3

# Or using virtual environment
python3 -m venv bigip_scanner_env
source bigip_scanner_env/bin/activate
pip install requests urllib3
```

### Installation Options

| Option | Description |
|--------|-------------|
| `--skip-system-deps` | Skip system package installation (for restricted environments) |
| `--python-only` | Only install Python dependencies |
| `--test-only` | Only run tests (skip installation) |
| `--help` | Show installation help |

## Usage

### Basic Usage

```bash
# Interactive mode
python bigscan.py

# With credentials
python bigscan.py --user admin

# Complete example
python bigscan.py --user admin --pass mypassword --out results.csv
```

### Bulk Processing

```bash
# Process multiple devices from CSV
python bigscan.py --in devices.csv --out results.csv

# With fallback credentials
python bigscan.py --in devices.csv --user admin --out audit_results.csv
```

## Command Line Options

### Main Script (`bigscan.py`)

| Option | Short | Description | Example |
|--------|-------|-------------|---------|
| `--user` | `-u` | Username for authentication | `--user admin` |
| `--pass` | `-p` | Password for authentication | `--pass mypassword` |
| `--out` | `-o` | Output CSV filename | `--out devices.csv` |
| `--in` | `-i` | Input CSV filename | `--in device_list.csv` |
| `--help` | `-h` | Show help message | `--help` |

**Security Note**: Using `--pass` in command line is not recommended as passwords may be visible in process lists and command history.

### Installation Script (`install.sh`)

| Option | Description |
|--------|-------------|
| `--skip-system-deps` | Skip system package installation |
| `--python-only` | Only install Python dependencies |
| `--test-only` | Only run tests (skip installation) |
| `--help` | Show installation help |

## Input CSV Format

Create a CSV file with device information for bulk processing:

```csv
ip,username,password
10.100.100.30,admin,mypassword
10.100.100.31,root,
192.168.1.100,,
172.16.1.50,user1,pass123
```

### CSV Format Rules

- **IP Address** (required): First column, BIG-IP device IP or hostname
- **Username** (optional): Second column, leave empty to use command line `--user` or prompt
- **Password** (optional): Third column, leave empty to use command line `--pass` or prompt
- **Headers**: Optional, script auto-detects headers
- **Empty rows**: Automatically skipped

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
| `system_time` | Current system time | `Wed Jul 14 12:34:56 UTC 2025` |
| `total_memory` | Total system memory | `8GB` |
| `cpu_count` | Number of CPUs | `4` |
| `ha_status` | High availability status | `Standalone` |
| `extraction_timestamp` | When data was collected | `2025-07-14 12:34:56` |

## Examples

### Single Device

```bash
# Interactive mode
python bigscan.py
Enter BIG-IP device IP/hostname: 10.100.100.30
Enter username: admin
Enter password: ********

# Command line mode
python bigscan.py --user admin --out single_device.csv
```

### Multiple Devices

```bash
# Create input file
cat > devices.csv << EOF
ip,username,password
10.100.100.30,admin,secret123
10.100.100.31,root,
192.168.1.100,,
EOF

# Process all devices
python bigscan.py --in devices.csv --user fallback_admin --out results.csv
```

### Production Examples

```bash
# Weekly audit with timestamp
python bigscan.py --in production_devices.csv --out audit_$(date +%Y%m%d).csv

# Department-specific scan
python bigscan.py --in datacenter_devices.csv --user audit_account --out datacenter_audit.csv

# Emergency hotfix check
python bigscan.py --in critical_devices.csv --out hotfix_status.csv
```

## Troubleshooting

### Common Issues

#### Authentication Failures
```bash
# Test authentication manually
python bigscan.py --user admin
```

#### Missing Dependencies
```bash
# Reinstall dependencies
./install.sh --python-only
```

#### API Connection Issues
```bash
# Use debug mode
python bigscan.py
# Choose debug mode when prompted
```

### Debug Modes

The script includes built-in debugging capabilities:

1. **API Structure Debug**: Explore available REST API endpoints
2. **Serial Number Debug**: Detailed search for chassis serial numbers
3. **Verbose Output**: Shows API calls and responses during extraction

### Error Messages

| Error | Cause | Solution |
|-------|--------|----------|
| `401 Unauthorized` | Invalid credentials | Check username/password |
| `Connection refused` | Network/firewall issue | Verify IP and network connectivity |
| `Module not found` | Missing dependencies | Run `./install.sh` |
| `File not found` | Missing input CSV | Check file path and permissions |

## System Requirements

### Supported Platforms
- **Linux**: Ubuntu, RHEL, CentOS, Fedora, Arch Linux
- **macOS**: 10.14+ with Homebrew
- **Windows**: Windows 10+ with Python 3.7+

### Dependencies
- **Python**: 3.7 or higher
- **Python Packages**: 
  - `requests` (HTTP client for REST API)
  - `urllib3` (HTTP library, dependency of requests)
- **System Packages**: 
  - `python3-pip` (package installer)
  - `python3-venv` (virtual environment support)

### F5 BIG-IP Compatibility
- **TMOS**: 12.0+ (tested on 16.x, 17.x)
- **Access**: Management interface access required
- **Permissions**: Read-only access sufficient
- **Protocols**: HTTPS (port 443)

## Security Considerations

### Authentication Security
- **Token-based**: Uses F5's secure token authentication
- **Password Handling**: Passwords never stored, only used for token generation
- **Command Line**: Avoid `--pass` in production scripts
- **CSV Storage**: Secure CSV files containing credentials appropriately

### Network Security
- **HTTPS Only**: All communications encrypted
- **Certificate Validation**: Disabled for self-signed certificates (common with BIG-IP)
- **Firewall**: Ensure port 443 access to BIG-IP management interface

### Best Practices
1. Use service accounts with minimal required permissions
2. Store credential CSV files securely with restricted permissions
3. Use virtual environments to isolate dependencies
4. Regularly rotate service account credentials
5. Audit script usage and output file access

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
```

### Adding New Features
The script is modular and can be extended:
- Add new data extraction methods to the `BigIPInfoExtractor` class
- Extend CSV output by modifying the `write_to_csv()` function
- Add new command line options in the `main()` function

## License

This project is provided as-is for educational and administrative purposes. Please ensure compliance with your organization's security policies and F5's terms of service when using this tool.

## Support

For issues and questions:
1. Check the troubleshooting section above
2. Run debug mode for API-related issues
3. Use the installation test script to verify setup
4. Check F5 documentation for REST API changes

---

**Last Updated**: July 2025  
**Version**: 1.0  
**Tested with**: TMOS 16.1.x, 17.1.x