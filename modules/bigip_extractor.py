"""
BIG-IP Information Extractor

This module handles connection to F5 BIG-IP devices and extracts comprehensive system information
including hostname, serial number, registration key, software version, hotfixes, and more.
Also includes QKView creation and download functionality.
"""

import json
import os
import time
from datetime import datetime
import requests
import urllib3

from .colors import Colors
from .auth_handler import BigIPAuthHandler
from .qkview_handler import QKViewHandler
from .support_lifecycle import get_support_processor

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class BigIPInfoExtractor:
    def __init__(self, host, username, password, create_qkview=False, qkview_timeout=1200, no_delete=False, verbose=False):
        """Initialize connection to BIG-IP device"""
        self.host = host
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.verify = False
        self.base_url = f"https://{self.host}"
        self.device_info = {}
        self.create_qkview = create_qkview
        self.qkview_timeout = qkview_timeout
        self.no_delete = no_delete
        self.verbose = verbose
        
        # Initialize authentication handler
        self.auth_handler = BigIPAuthHandler(
            host, username, password, self.session, verbose
        )
        
        # Initialize QKView handler
        if create_qkview:
            self.qkview_handler = QKViewHandler(
                self.session, 
                self.base_url, 
                qkview_timeout, 
                no_delete,
                verbose
            )
    
    @property
    def token(self):
        """Get the current authentication token"""
        return self.auth_handler.get_token()
    
    def api_request(self, endpoint):
        """Make authenticated API request"""
        try:
            url = f"{self.base_url}/mgmt/tm/{endpoint}"
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"API request failed for {endpoint}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error making API request to {endpoint}: {str(e)}")
            return None
    
    def api_request_selflink(self, selflink_url):
        """Make authenticated API request using selfLink URL"""
        try:
            # selfLink URLs are full URLs, so use them directly
            response = self.session.get(selflink_url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                return data
            else:
                print(f"SelfLink request failed for {selflink_url}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error making selfLink request to {selflink_url}: {str(e)}")
            return None
    
    def connect(self):
        """Establish connection to BIG-IP device"""
        return self.auth_handler.get_auth_token()
    
    def logout(self):
        """Logout and cleanup session"""
        self.auth_handler.logout()
    
    def get_system_info(self):
        """Extract basic system information"""
        try:
            # Get system info
            system_data = self.api_request("sys/global-settings")
            if system_data:
                self.device_info['hostname'] = system_data.get('hostname', 'N/A')
            else:
                self.device_info['hostname'] = 'N/A'
            
            # Get platform info from sys/hardware
            print("    Extracting platform information...")
            hardware_data = self.api_request("sys/hardware")
            if hardware_data:
                platform = self._extract_platform_from_hardware(hardware_data)
                if platform:
                    self.device_info['platform'] = platform
                    if self.verbose:
                        print(f"      Found platform: {platform}")
                else:
                    self.device_info['platform'] = 'N/A'
            else:
                self.device_info['platform'] = 'N/A'
            
        except Exception as e:
            print(f"Error getting system info: {str(e)}")
            self.device_info['hostname'] = 'N/A'
            self.device_info['platform'] = 'N/A'
    
    def _extract_platform_from_hardware(self, hardware_data):
        """Extract platform information from sys/hardware response"""
        try:
            if not hardware_data or 'entries' not in hardware_data:
                return None
            
            entries = hardware_data['entries']
            
            # Method 1: Look in system-info section for platform
            for entry_url, entry_data in entries.items():
                if 'system-info' in entry_url:
                    if self.verbose:
                        print(f"      Checking system-info for platform: {entry_url}")
                    else:
                        print(f"      Checking system-info for platform...")
                    
                    nested_stats = entry_data.get('nestedStats', {})
                    nested_entries = nested_stats.get('entries', {})
                    
                    for nested_url, nested_data in nested_entries.items():
                        if 'system-info/0' in nested_url:
                            system_stats = nested_data.get('nestedStats', {})
                            system_entries = system_stats.get('entries', {})
                            
                            # Look for platform field
                            if 'platform' in system_entries:
                                platform_info = system_entries['platform']
                                if isinstance(platform_info, dict) and 'description' in platform_info:
                                    platform = platform_info['description']
                                    return platform
            
            return None
            
        except Exception as e:
            print(f"      Error extracting platform: {str(e)}")
            return None
    
    def get_device_serial(self):
        """Extract device serial number"""
        try:
            
            # Check sys/hardware directly for bigipChassisSerialNum
            if self.verbose:
                print("      Checking sys/hardware for bigipChassisSerialNum...")
            hardware_data = self.api_request("sys/hardware")
            
            if hardware_data:
                # Extract it properly from the structure
                serial = self._extract_chassis_serial_from_hardware(hardware_data)
                if serial:
                    self.device_info['serial_number'] = serial
                    print(f"      {Colors.green('✓')} Found chassis serial: {serial}")
                    return
                
                # Also try to extract bigipChassisSerialNum recursively
                serial = self._find_bigip_chassis_serial(hardware_data)
                if serial:
                    self.device_info['serial_number'] = serial
                    print(f"      {Colors.green('✓')} Found bigipChassisSerialNum: {serial}")
                    return
            
            print("    Chassis serial number not found")
            self.device_info['serial_number'] = 'N/A'
            
        except Exception as e:
            print(f"Error getting serial number: {str(e)}")
            self.device_info['serial_number'] = 'N/A'
    
    def _extract_chassis_serial_from_hardware(self, hardware_data):
        """Extract chassis serial from sys/hardware response structure"""
        try:
            if not hardware_data or 'entries' not in hardware_data:
                return None
            
            # Navigate the structure: entries -> system-info -> system-info/0 -> bigipChassisSerialNum
            entries = hardware_data['entries']
            
            for entry_url, entry_data in entries.items():
                if 'system-info' in entry_url:
                    if self.verbose:
                        print(f"      Found system-info entry: {entry_url}")
                    
                    nested_stats = entry_data.get('nestedStats', {})
                    nested_entries = nested_stats.get('entries', {})
                    
                    for nested_url, nested_data in nested_entries.items():
                        if 'system-info/0' in nested_url:
                            if self.verbose:
                                print(f"      Found system-info/0 entry: {nested_url}")
                            
                            system_stats = nested_data.get('nestedStats', {})
                            system_entries = system_stats.get('entries', {})
                            
                            if 'bigipChassisSerialNum' in system_entries:
                                chassis_serial_info = system_entries['bigipChassisSerialNum']
                                if isinstance(chassis_serial_info, dict) and 'description' in chassis_serial_info:
                                    serial = chassis_serial_info['description']
                                    if self.verbose:
                                        print(f"      Found bigipChassisSerialNum: {serial}")
                                    return serial
            
            return None
            
        except Exception as e:
            print(f"      Error extracting chassis serial: {str(e)}")
            return None
    
    def _find_bigip_chassis_serial(self, data):
        """Recursively search for bigipChassisSerialNum in any data structure"""
        if isinstance(data, dict):
            for key, value in data.items():
                if key == 'bigipChassisSerialNum':
                    if isinstance(value, dict) and 'description' in value:
                        return value['description']
                    elif isinstance(value, str):
                        return value
                elif isinstance(value, (dict, list)):
                    result = self._find_bigip_chassis_serial(value)
                    if result:
                        return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_bigip_chassis_serial(item)
                if result:
                    return result
        
        return None
    
    def get_registration_key(self):
        """Extract registration key information"""
        try:
            print("    Searching for registration key...")
            
            # Check sys/license for registrationKey
            if self.verbose:
                print("      Checking sys/license for registration key...")
            license_data = self.api_request("sys/license")
            
            if license_data:
                if self.verbose:
                    print(f"        Searching license data for registration key...")
                
                # Look for the registration key in the structured data
                reg_key = self._extract_registration_key_from_license(license_data)
                if reg_key:
                    self.device_info['registration_key'] = reg_key
                    print(f"    {Colors.green('✓')} Found registration key: {reg_key}")
                    return
            
            print("    Registration key not found")
            self.device_info['registration_key'] = 'N/A'
            
        except Exception as e:
            print(f"Error getting registration key: {str(e)}")
            self.device_info['registration_key'] = 'N/A'
    
    def _extract_registration_key_from_license(self, license_data):
        """Extract registration key from sys/license response structure"""
        try:
            if not license_data or 'entries' not in license_data:
                return None
            
            # Navigate the structure: entries -> license/0 -> registrationKey
            entries = license_data['entries']
            
            for entry_url, entry_data in entries.items():
                if 'license/0' in entry_url or 'license' in entry_url:
                    if self.verbose:
                        print(f"      Found license entry: {entry_url}")
                    
                    nested_stats = entry_data.get('nestedStats', {})
                    nested_entries = nested_stats.get('entries', {})
                    
                    # Look for registrationKey field
                    for field_name, field_data in nested_entries.items():
                        if 'registrationkey' in field_name.lower() or 'registration' in field_name.lower():
                            if self.verbose:
                                print(f"      Found registration field: {field_name}")
                            
                            if isinstance(field_data, dict) and 'description' in field_data:
                                reg_key = field_data['description']
                                if reg_key and reg_key.strip() and reg_key != '-':
                                    if self.verbose:
                                        print(f"      Registration key value: {reg_key}")
                                    return reg_key.strip()
            
            return None
            
        except Exception as e:
            print(f"      Error extracting registration key: {str(e)}")
            return None
    
    def get_software_version(self):
        """Extract software version information"""
        try:
            active_version = 'N/A'
            available_versions = []
            
            # Try sys/software/volume for boot locations
            print("    Checking for boot locations...")
            volume_data = self.api_request("sys/software/volume")
            
            if volume_data and 'items' in volume_data:
                print(f"    Found {len(volume_data['items'])} boot locations")
                
                for volume in volume_data['items']:
                    volume_name = volume.get('name', 'Unknown')
                    volume_version = volume.get('version', 'Unknown')
                    volume_product = volume.get('product', '')
                    is_active = volume.get('active', False)
                    
                    # Create a descriptive string for this boot location
                    if volume_product:
                        volume_info = f"{volume_name} ({volume_version}) - {volume_product}"
                    else:
                        volume_info = f"{volume_name} ({volume_version})"
                    
                    available_versions.append(volume_info)
                    print(f"      Boot location: {volume_info} {'[ACTIVE]' if is_active else ''}")
                    
                    if is_active:
                        active_version = volume_version
                        if self.verbose:
                            print(f"    Active version: {active_version}")
            
            # Fallback: Try sys/version for TMOS version if no active version
            if active_version == 'N/A':
                print("    Trying sys/version for TMOS info...")
                tmos_data = self.api_request("sys/version")
                if tmos_data and 'entries' in tmos_data:
                    for entry_name, entry_data in tmos_data['entries'].items():
                        nested_stats = entry_data.get('nestedStats', {})
                        entries = nested_stats.get('entries', {})
                        
                        if 'Version' in entries:
                            version_info = entries['Version'].get('description', '')
                            if version_info and version_info != 'N/A':
                                active_version = version_info
                                if self.verbose:
                                    print(f"    Found version: {active_version}")
                                break
            
            # Check for additional software information
            print("    Checking for additional software information...")
            
            self.device_info['active_version'] = active_version
            self.device_info['available_versions'] = '; '.join(available_versions) if available_versions else 'N/A'
            
            print(f"    Active Boot Location Version: {active_version}")
            print(f"    Available Boot Locations: {len(available_versions)}")
            
        except Exception as e:
            print(f"Error getting software version: {str(e)}")
            self.device_info['active_version'] = 'N/A'
            self.device_info['available_versions'] = 'N/A'
    
    def get_hotfix_info(self):
        """Extract hotfix information"""
        try:
            print("    Extracting hotfix information...")
            
            hotfix_list = []
            emergency_hotfixes = []
            
            # Get hotfix information from sys/software/hotfix
            hotfix_data = self.api_request("sys/software/hotfix")
            
            if hotfix_data:
                # Show full REST response only with verbose flag
                if self.verbose:
                    print(f"      REST API Response: {json.dumps(hotfix_data, indent=2)}")
                
                if 'items' in hotfix_data and hotfix_data['items']:
                    hotfix_count = len(hotfix_data['items'])
                    print(f"      {Colors.green(f'Found {hotfix_count} hotfix(es) installed:')}")
                    
                    for i, hotfix in enumerate(hotfix_data['items'], 1):
                        # Extract key fields
                        name = hotfix.get('name', 'Unknown')
                        hotfix_id = hotfix.get('id', 'N/A')
                        title = hotfix.get('title', 'N/A')
                        version = hotfix.get('version', 'Unknown')
                        product = hotfix.get('product', '')
                        
                        # Create details line for second row
                        details = []
                        if title != 'N/A':
                            details.append(title)
                        if hotfix_id != 'N/A':
                            details.append(f"ID {hotfix_id}")
                        
                        details_line = ""
                        if details:
                            details_line = f"[{' ('.join(details)}"
                            if len(details) > 1:
                                details_line += ")"
                            details_line += "]"
                        
                        # Check if it's an emergency hotfix
                        name_lower = name.lower()
                        title_lower = title.lower() if title != 'N/A' else ''
                        id_lower = hotfix_id.lower() if hotfix_id != 'N/A' else ''
                        
                        is_emergency = any(keyword in name_lower for keyword in ['emergency', 'critical', 'hotfix', 'ehf', 'hf', 'eng']) or \
                                      any(keyword in title_lower for keyword in ['emergency', 'critical', 'hotfix', 'ehf', 'hf', 'eng']) or \
                                      any(keyword in id_lower for keyword in ['hf', 'ehf', 'eng'])
                        
                        # Display the hotfix with proper colors and two-line format
                        if is_emergency:
                            # Red ⚠ and yellow text
                            print(f"        {Colors.red('⚠')} {Colors.yellow(name)}")
                            if details_line:
                                print(f"            {Colors.yellow(details_line)}")
                        else:
                            # Regular bullet point
                            print(f"        • {name}")
                            if details_line:
                                print(f"            {details_line}")
                        
                        # Create hotfix info string for CSV
                        if product:
                            hotfix_info = f"{name} ({version}) - {product}"
                        else:
                            hotfix_info = f"{name} ({version})"
                        
                        # Add ID and title to the CSV info if available
                        if hotfix_id != 'N/A' and title != 'N/A':
                            hotfix_info += f" [ID: {hotfix_id}, Title: {title}]"
                        elif hotfix_id != 'N/A':
                            hotfix_info += f" [ID: {hotfix_id}]"
                        elif title != 'N/A':
                            hotfix_info += f" [Title: {title}]"
                        
                        hotfix_list.append(hotfix_info)
                        
                        if is_emergency:
                            emergency_hotfixes.append(hotfix_info)
                else:
                    print(f"      {Colors.green('No hotfixes installed')}")
            else:
                print(f"      {Colors.green('No hotfix data returned from API')}")
            
            # Set device info for CSV output
            if hotfix_list:
                self.device_info['installed_hotfixes'] = '; '.join(hotfix_list)
                print(f"      Summary: {len(hotfix_list)} hotfix(es) total")
            else:
                self.device_info['installed_hotfixes'] = 'None'
            
            if emergency_hotfixes:
                self.device_info['emergency_hotfixes'] = '; '.join(emergency_hotfixes)
                print(f"      Emergency/Critical: {len(emergency_hotfixes)} hotfix(es)")
            else:
                self.device_info['emergency_hotfixes'] = 'None'
            
        except Exception as e:
            print(f"      Error getting hotfix info: {str(e)}")
            if self.verbose:
                import traceback
                print(f"      Traceback: {traceback.format_exc()}")
            self.device_info['installed_hotfixes'] = 'N/A'
            self.device_info['emergency_hotfixes'] = 'N/A'
    
    def get_additional_info(self):
        """Extract additional useful information"""
        try:
            # System clock/time - improved
            print("    Getting system time...")
            self._get_system_time_improved()
            
            # Memory information - improved
            print("    Getting memory information...")
            self._get_memory_info_improved()
            
            # CPU information
            print("    Getting CPU information...")
            cpu_data = self.api_request("sys/cpu")
            if cpu_data and 'entries' in cpu_data:
                cpu_count = len(cpu_data['entries'])
                self.device_info['cpu_count'] = cpu_count
                print(f"      Found {cpu_count} CPU entries")
            else:
                self.device_info['cpu_count'] = 'N/A'
                print("      CPU data not available")
            
            # HA status - improved
            print("    Getting HA status...")
            self._get_ha_status_improved()
            
            # Management IP
            self.device_info['management_ip'] = self.host
            
        except Exception as e:
            print(f"Error getting additional info: {str(e)}")
            self.device_info.update({
                'system_time': 'N/A',
                'total_memory': 'N/A',
                'memory_used': 'N/A',
                'tmm_memory': 'N/A',
                'cpu_count': 'N/A',
                'ha_status': 'N/A',
                'management_ip': self.host
            })
    
    def _get_system_time_improved(self):
        """Improved system time extraction with multiple methods"""
        self.device_info['system_time'] = 'N/A'
        
        # Method 1: Try sys/clock for various time fields
        clock_data = self.api_request("sys/clock")
        if clock_data:
            time_fields = ['fullDate', 'date', 'time', 'dateTime']
            for field in time_fields:
                if field in clock_data and clock_data[field]:
                    raw_time = clock_data[field]
                    formatted_time = self._format_system_time(raw_time)
                    if formatted_time != 'N/A':
                        self.device_info['system_time'] = formatted_time
                        print(f"      Found system time: {formatted_time}")
                        return
        
        # Method 2: Try getting from sys/global-settings
        try:
            global_data = self.api_request("sys/global-settings")
            if global_data and 'consoleInactivityTimeout' in global_data:
                # Device is responding, use current timestamp as fallback
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.device_info['system_time'] = current_time
                print(f"      Using local timestamp: {current_time}")
                return
        except Exception as e:
            if self.verbose:
                print(f"      Error getting fallback time: {str(e)}")
        
        print("      Could not determine system time")
    
    def _get_memory_info_improved(self):
        """Improved memory information extraction with better fallbacks"""
        # Initialize memory fields
        self.device_info.update({
            'total_memory': 'N/A',
            'memory_used': 'N/A', 
            'tmm_memory': 'N/A'
        })
        
        # Method 1: Try sys/tmm-info for TMM memory (this works!)
        if self.verbose:
            print("      Trying sys/tmm-info for TMM memory...")
        tmm_info = self.api_request("sys/tmm-info")
        if tmm_info and 'entries' in tmm_info:
            for entry_name, entry_data in tmm_info['entries'].items():
                if 'nestedStats' in entry_data:
                    nested_entries = entry_data['nestedStats'].get('entries', {})
                    for field_name, field_data in nested_entries.items():
                        if 'memory' in field_name.lower() and isinstance(field_data, dict):
                            value = field_data.get('description') or field_data.get('value')
                            if value and str(value).replace('.', '').isdigit():
                                formatted_mem = self._format_memory_value(value)
                                self.device_info['tmm_memory'] = formatted_mem
                                if self.verbose:
                                    print(f"      Found TMM memory: {formatted_mem}")
                                break
        
        # Method 2: Try sys/host-info for host memory
        if self.verbose:
            print("      Trying sys/host-info for host memory...")
        host_info = self.api_request("sys/host-info")
        if host_info and 'entries' in host_info:
            for entry_name, entry_data in host_info['entries'].items():
                if 'nestedStats' in entry_data:
                    nested_entries = entry_data['nestedStats'].get('entries', {})
                    for field_name, field_data in nested_entries.items():
                        if 'memory' in field_name.lower() and isinstance(field_data, dict):
                            value = field_data.get('description') or field_data.get('value')
                            if value:
                                formatted_mem = self._format_memory_value(value)
                                if 'total' in field_name.lower() and self.device_info['total_memory'] == 'N/A':
                                    self.device_info['total_memory'] = formatted_mem
                                    if self.verbose:
                                        print(f"      Found total memory: {formatted_mem}")
                                elif 'used' in field_name.lower() and self.device_info['memory_used'] == 'N/A':
                                    self.device_info['memory_used'] = formatted_mem
                                    if self.verbose:
                                        print(f"      Found used memory: {formatted_mem}")
        
        # Method 3: Try sys/platform for memory info
        if self.device_info['total_memory'] == 'N/A':
            print("      Trying sys/platform for memory...")
            platform_info = self.api_request("sys/platform")
            if platform_info and 'entries' in platform_info:
                for entry_name, entry_data in platform_info['entries'].items():
                    if 'nestedStats' in entry_data:
                        nested_entries = entry_data['nestedStats'].get('entries', {})
                        for field_name, field_data in nested_entries.items():
                            if 'memory' in field_name.lower() and isinstance(field_data, dict):
                                value = field_data.get('description') or field_data.get('value')
                                if value:
                                    formatted_mem = self._format_memory_value(value)
                                    if formatted_mem != 'N/A' and self.device_info['total_memory'] == 'N/A':
                                        self.device_info['total_memory'] = formatted_mem
                                        print(f"      Found memory in platform: {formatted_mem}")
                                        break
        
        print(f"      Memory Results: Total={self.device_info['total_memory']}, Used={self.device_info['memory_used']}, TMM={self.device_info['tmm_memory']}")
    
    def _get_ha_status_improved(self):
        """Improved HA status detection with multiple methods"""
        self.device_info['ha_status'] = 'N/A'
        
        # Method 1: Try sys/failover
        try:
            failover_data = self.api_request("sys/failover")
            if failover_data:
                if 'status' in failover_data:
                    self.device_info['ha_status'] = failover_data['status']
                    print(f"      Found HA status: {failover_data['status']}")
                    return
                elif 'entries' in failover_data:
                    for entry_name, entry_data in failover_data['entries'].items():
                        nested_stats = entry_data.get('nestedStats', {})
                        entries = nested_stats.get('entries', {})
                        
                        for field_name, field_data in entries.items():
                            if 'status' in field_name.lower() and isinstance(field_data, dict):
                                status_value = field_data.get('description') or field_data.get('value')
                                if status_value:
                                    self.device_info['ha_status'] = status_value
                                    print(f"      Found HA status in entries: {status_value}")
                                    return
        except Exception as e:
            if self.verbose:
                print(f"      Error checking sys/failover: {str(e)}")
        
        # Method 2: Try cm/device to check for clustering
        try:
            device_data = self.api_request("cm/device")
            if device_data and 'items' in device_data:
                device_count = len(device_data['items'])
                if device_count > 1:
                    self.device_info['ha_status'] = f'Clustered ({device_count} devices)'
                    print(f"      Found clustering: {device_count} devices")
                    return
                else:
                    self.device_info['ha_status'] = 'Standalone'
                    print(f"      Single device detected: Standalone")
                    return
        except Exception as e:
            if self.verbose:
                print(f"      Error checking cm/device: {str(e)}")
        
        # Method 3: Default to Standalone
        self.device_info['ha_status'] = 'Standalone'
        print(f"      Using default: Standalone")
    
    def _format_memory_value(self, memory_value):
        """Convert memory value to a readable format"""
        if not memory_value or memory_value == 'N/A':
            return 'N/A'
        
        try:
            # Convert to string and clean up
            mem_str = str(memory_value).strip()
            
            # If it's already a number in bytes, convert to GB
            if mem_str.isdigit():
                bytes_value = int(mem_str)
                gb_value = bytes_value / (1024 * 1024 * 1024)
                if gb_value >= 1:
                    return f"{gb_value:.1f}GB"
                else:
                    mb_value = bytes_value / (1024 * 1024)
                    return f"{mb_value:.1f}MB"
            
            # If it already has units, return as-is
            if any(unit in mem_str.upper() for unit in ['GB', 'MB', 'KB', 'TB']):
                return mem_str
            
            # Try to extract numeric value and convert
            import re
            numeric_match = re.search(r'(\d+(?:\.\d+)?)', mem_str)
            if numeric_match:
                numeric_value = float(numeric_match.group(1))
                
                # Assume it's in bytes if it's a large number
                if numeric_value > 1000000:  # Likely bytes
                    gb_value = numeric_value / (1024 * 1024 * 1024)
                    if gb_value >= 1:
                        return f"{gb_value:.1f}GB"
                    else:
                        mb_value = numeric_value / (1024 * 1024)
                        return f"{mb_value:.1f}MB"
                else:
                    # Might already be in MB or GB
                    return mem_str
            
            # If we can't parse it, return original
            return mem_str
            
        except Exception as e:
            print(f"        Error formatting memory value '{memory_value}': {str(e)}")
            return str(memory_value)
    
    def _format_system_time(self, time_string):
        """Convert system time to standard format in local timezone (YYYY-MM-DD HH:MM:SS)"""
        if not time_string or time_string.strip() == '':
            return 'N/A'
        
        try:
            from datetime import datetime, timezone
            
            # Common BIG-IP time formats to try
            time_formats = [
                ('%Y-%m-%dT%H:%M:%SZ', True),         # 2025-07-15T03:28:35Z (ISO 8601 UTC)
                ('%Y-%m-%dT%H:%M:%S', False),         # 2025-07-15T03:28:35 (assume local)
                ('%Y-%m-%d %H:%M:%S', False),         # 2025-07-14 15:30:45 (assume local)
                ('%a %b %d %H:%M:%S %Z %Y', True),    # Wed Jul 14 15:30:45 UTC 2025
                ('%a %b %d %H:%M:%S %Y', False),      # Wed Jul 14 15:30:45 2025 (assume local)
            ]
            
            time_string = time_string.strip()
            
            # Try each format
            for fmt, is_utc in time_formats:
                try:
                    dt = datetime.strptime(time_string, fmt)
                    
                    if is_utc:
                        # Convert from UTC to local timezone
                        dt = dt.replace(tzinfo=timezone.utc)
                        local_dt = dt.astimezone()
                        formatted_time = local_dt.strftime('%Y-%m-%d %H:%M:%S')
                        print(f"      Converted UTC time: {time_string} -> {formatted_time} (local)")
                    else:
                        # Assume it's already in local time
                        formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                        print(f"      Converted local time: {time_string} -> {formatted_time}")
                    
                    return formatted_time
                except ValueError:
                    continue
            
            # If all else fails, return the original string
            return time_string
            
        except Exception as e:
            print(f"      Error formatting time '{time_string}': {str(e)}")
            return time_string
    
    def _get_support_lifecycle_info(self):
        """Get F5 software support lifecycle information"""
        try:
            active_version = self.device_info.get('active_version', 'N/A')
            
            if active_version and active_version != 'N/A':
                support_processor = get_support_processor(verbose=self.verbose)
                support_info = support_processor.get_version_support_info(active_version)
                
                if support_info['found']:
                    self.device_info['support_status'] = support_info['support_status']
                    self.device_info['support_phase'] = support_info['support_phase']
                    self.device_info['end_of_software_development'] = support_info.get('end_of_software_development', 'N/A')
                    self.device_info['end_of_technical_support'] = support_info.get('end_of_technical_support', 'N/A')
                    self.device_info['support_urgency'] = support_info['urgency']
                    self.device_info['support_recommendation'] = support_info['recommendation']
                    
                    if self.verbose:
                        print(f"      Support Status: {support_info['support_status']}")
                        print(f"      Support Phase: {support_info['support_phase']}")
                        print(f"      Urgency: {support_info['urgency']}")
                    elif support_info['urgency'] in ['High', 'Critical']:
                        print(f"      {Colors.yellow('⚠')} Support Status: {support_info['support_status']} - {support_info['urgency']} priority")
                    else:
                        print(f"      Support Status: {support_info['support_status']}")
                else:
                    self.device_info['support_status'] = 'Unknown'
                    self.device_info['support_phase'] = 'Unknown'
                    self.device_info['end_of_software_development'] = 'N/A'
                    self.device_info['end_of_technical_support'] = 'N/A'
                    self.device_info['support_urgency'] = 'Unknown'
                    self.device_info['support_recommendation'] = 'Verify version number and check F5 documentation'
                    print(f"      Support Status: Unknown (version not in database)")
            else:
                self.device_info['support_status'] = 'N/A'
                self.device_info['support_phase'] = 'N/A'
                self.device_info['end_of_software_development'] = 'N/A'
                self.device_info['end_of_technical_support'] = 'N/A'
                self.device_info['support_urgency'] = 'N/A'
                self.device_info['support_recommendation'] = 'N/A'
                
        except Exception as e:
            print(f"      Error getting support lifecycle info: {str(e)}")
            self.device_info['support_status'] = 'Error'
            self.device_info['support_phase'] = 'Error'
            self.device_info['end_of_software_development'] = 'Error'
            self.device_info['end_of_technical_support'] = 'Error'
            self.device_info['support_urgency'] = 'Error'
            self.device_info['support_recommendation'] = 'Error retrieving support information'
    
    def extract_all_info(self):
        """Extract all device information"""
        if not self.connect():
            return False
        
        print("  Extracting system information...")
        self.get_system_info()
        
        print("    Extracting device serial number...")
        self.get_device_serial()
        
        print("    Extracting registration key...")
        self.get_registration_key()
        
        print("    Extracting software version...")
        self.get_software_version()
        
        # Extract hotfix information (called only once here)
        self.get_hotfix_info()
        
        print("  Extracting additional information...")
        self.get_additional_info()
        
        # Get F5 software support lifecycle information
        print("  Getting F5 software support lifecycle information...")
        self._get_support_lifecycle_info()
        
        # Create and download QKView if requested
        if self.create_qkview:
            if self.verbose:
                print("  Creating QKView using F5 autodeploy endpoint...")
                print(f"  QKView timeout configured for: {self.qkview_timeout} seconds ({self.qkview_timeout/60:.1f} minutes)")
            else:
                print("  Creating and downloading QKView...")
            
            # Set token in QKView handler
            self.qkview_handler.set_token(self.auth_handler.get_token())
            
            # Update device info in QKView handler
            self.qkview_handler.set_device_info(self.device_info)
            
            qkview_success = self.qkview_handler.create_and_download_qkview()
            self.device_info['qkview_downloaded'] = 'Yes' if qkview_success else 'Failed'
        else:
            self.device_info['qkview_downloaded'] = 'Not requested'
        
        # Add extraction timestamp
        self.device_info['extraction_timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Clean up session
        self.logout()
        
        return True

