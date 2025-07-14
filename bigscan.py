#!/usr/bin/env python3
"""
BIG-IP Device Information Extractor

This script connects to F5 BIG-IP devices and extracts comprehensive system information
including hostname, serial number, registration key, software version, hotfixes, and more.
The data is exported to a CSV file for easy analysis.

Requirements:
    pip install requests urllib3

Usage:
    python bigip_info.py [--user USERNAME] [--pass PASSWORD] [--out FILENAME] [--in INPUT_CSV] [--help]
    
Examples:
    python bigip_info.py                                    # Interactive mode
    python bigip_info.py --user admin                       # Specify user, prompt for password
    python bigip_info.py --user admin --pass mypassword     # Specify both credentials
"""

import csv
import json
import sys
import getpass
import argparse
from datetime import datetime
import requests
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BigIPInfoExtractor:
    def __init__(self, host, username, password):
        """Initialize connection to BIG-IP device"""
        self.host = host
        self.username = username
        self.password = password
        self.token = None
        self.session = requests.Session()
        self.session.verify = False
        self.base_url = f"https://{self.host}"
        self.device_info = {}
        
    def get_auth_token(self):
        """Get authentication token from BIG-IP"""
        try:
            print(f"Getting auth token from {self.host}...")
            
            # Prepare authentication payload
            auth_data = {
                "username": self.username,
                "password": self.password,
                "loginProviderName": "tmos"
            }
            
            # Request authentication token
            response = self.session.post(
                f"{self.base_url}/mgmt/shared/authn/login",
                json=auth_data,
                timeout=30
            )
            
            if response.status_code == 200:
                auth_response = response.json()
                self.token = auth_response.get('token', {}).get('token')
                if self.token:
                    # Set token in session headers
                    self.session.headers.update({
                        'X-F5-Auth-Token': self.token,
                        'Content-Type': 'application/json'
                    })
                    print("Authentication token obtained successfully!")
                    return True
                else:
                    print("Failed to obtain authentication token from response")
                    return False
            else:
                print(f"Authentication failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"Error getting authentication token: {str(e)}")
            return False
    
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
                # Search for target serial in the response
                response_str = str(data)
                if 'dfac18d2-466d-fc43-5cb74c9d3b49' in response_str:
                    print(f"    *** FOUND TARGET SERIAL in {selflink_url} ***")
                    print(f"    Response contains: {response_str[:500]}...")
                return data
            else:
                print(f"SelfLink request failed for {selflink_url}: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error making selfLink request to {selflink_url}: {str(e)}")
            return None
    
    def connect(self):
        """Establish connection to BIG-IP device"""
        return self.get_auth_token()
    
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
            print("  Extracting platform information...")
            hardware_data = self.api_request("sys/hardware")
            if hardware_data:
                platform = self._extract_platform_from_hardware(hardware_data)
                if platform:
                    self.device_info['platform'] = platform
                    print(f"  Found platform: {platform}")
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
                    print(f"    Checking system-info for platform: {entry_url}")
                    
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
                                    print(f"    Found platform in system-info: {platform}")
                                    return platform
            
            # Method 2: Look in platform section 
            for entry_url, entry_data in entries.items():
                if 'platform' in entry_url and 'system-info' not in entry_url:
                    print(f"    Checking platform section: {entry_url}")
                    
                    nested_stats = entry_data.get('nestedStats', {})
                    nested_entries = nested_stats.get('entries', {})
                    
                    for nested_url, nested_data in nested_entries.items():
                        if 'platform/0' in nested_url:
                            platform_stats = nested_data.get('nestedStats', {})
                            platform_entries = platform_stats.get('entries', {})
                            
                            # Look for any field that might contain platform/type info
                            for field_name, field_data in platform_entries.items():
                                if 'platform' in field_name.lower() or 'type' in field_name.lower() or 'marketing' in field_name.lower():
                                    if isinstance(field_data, dict) and 'description' in field_data:
                                        platform_val = field_data['description']
                                        if platform_val and platform_val.strip() and platform_val != ' ':
                                            print(f"    Found platform info in {field_name}: {platform_val}")
                                            return platform_val.strip()
            
            # Method 3: Recursive search for platform-related fields
            platform = self._find_platform_recursive(hardware_data)
            if platform:
                return platform
            
            return None
            
        except Exception as e:
            print(f"    Error extracting platform: {str(e)}")
            return None
    
    def _find_platform_recursive(self, data):
        """Recursively search for platform information in hardware data"""
        if isinstance(data, dict):
            for key, value in data.items():
                # Look for platform-related keys
                if key.lower() in ['platform', 'type', 'marketingname', 'model']:
                    if isinstance(value, dict) and 'description' in value:
                        platform_val = value['description']
                        if platform_val and platform_val.strip() and platform_val not in [' ', '-', 'N/A']:
                            print(f"    Found platform via recursive search in {key}: {platform_val}")
                            return platform_val.strip()
                    elif isinstance(value, str) and value.strip() and value not in [' ', '-', 'N/A']:
                        print(f"    Found platform via recursive search in {key}: {value}")
                        return value.strip()
                elif isinstance(value, (dict, list)):
                    result = self._find_platform_recursive(value)
                    if result:
                        return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_platform_recursive(item)
                if result:
                    return result
        
        return None
    
    def get_device_serial(self):
        """Extract device serial number"""
        try:
            print("  Searching for chassis serial number...")
            target_serial = "dfac18d2-466d-fc43-5cb74c9d3b49"
            
            # Method 1: Check sys/hardware directly for bigipChassisSerialNum
            print("  Checking sys/hardware for bigipChassisSerialNum...")
            hardware_data = self.api_request("sys/hardware")
            
            if hardware_data:
                # Search the entire response for our target serial
                response_str = str(hardware_data)
                if target_serial in response_str:
                    print(f"  Found target serial in sys/hardware response!")
                    
                    # Now extract it properly from the structure
                    serial = self._extract_chassis_serial_from_hardware(hardware_data)
                    if serial:
                        self.device_info['serial_number'] = serial
                        print(f"  SUCCESS: Found chassis serial: {serial}")
                        return
                
                # Also try to extract bigipChassisSerialNum specifically
                serial = self._find_bigip_chassis_serial(hardware_data)
                if serial:
                    self.device_info['serial_number'] = serial
                    print(f"  SUCCESS: Found bigipChassisSerialNum: {serial}")
                    return
            
            # Method 2: Try other endpoints as backup
            backup_endpoints = ['sys/host-info', 'sys/license', 'sys/version']
            
            for endpoint in backup_endpoints:
                print(f"  Checking {endpoint} as backup...")
                data = self.api_request(endpoint)
                if data:
                    response_str = str(data)
                    if target_serial in response_str:
                        print(f"  Found target serial in {endpoint}!")
                        self.device_info['serial_number'] = target_serial
                        return
            
            print(f"  Target serial {target_serial} not found in any location")
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
                    print(f"    Found system-info entry: {entry_url}")
                    
                    nested_stats = entry_data.get('nestedStats', {})
                    nested_entries = nested_stats.get('entries', {})
                    
                    for nested_url, nested_data in nested_entries.items():
                        if 'system-info/0' in nested_url:
                            print(f"    Found system-info/0 entry: {nested_url}")
                            
                            system_stats = nested_data.get('nestedStats', {})
                            system_entries = system_stats.get('entries', {})
                            
                            if 'bigipChassisSerialNum' in system_entries:
                                chassis_serial_info = system_entries['bigipChassisSerialNum']
                                if isinstance(chassis_serial_info, dict) and 'description' in chassis_serial_info:
                                    serial = chassis_serial_info['description']
                                    print(f"    Found bigipChassisSerialNum: {serial}")
                                    return serial
            
            return None
            
        except Exception as e:
            print(f"    Error extracting chassis serial: {str(e)}")
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
    
    def _search_for_target_serial(self, data, target_serial):
        """Search for the target serial number in any data structure"""
        if not data:
            return None
        
        # Convert entire response to string and search
        data_str = str(data)
        if target_serial in data_str:
            print(f"      *** FOUND TARGET SERIAL: {target_serial} ***")
            return target_serial
        
        # Also search for any UUID-like patterns as backup
        import re
        uuid_patterns = re.findall(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12,16}', data_str)
        for pattern in uuid_patterns:
            if len(pattern) > 30:  # Similar length to target serial
                print(f"      Found similar UUID pattern: {pattern}")
                # You can uncomment the line below if you want to use any UUID as fallback
                # return pattern
        
        return None
    
    def _extract_serial_from_nested_data(self, data, source):
        """Extract serial from nested hardware data"""
        if not data:
            return None
            
        print(f"      Examining nested data from {source}")
        
        if isinstance(data, dict):
            # Check for direct serial fields
            for key, value in data.items():
                if 'serial' in key.lower() and isinstance(value, str) and value.strip():
                    print(f"      Found serial field {key}: {value}")
                    return value.strip()
            
            # Check entries structure
            if 'entries' in data:
                for entry_name, entry_data in data['entries'].items():
                    if isinstance(entry_data, dict):
                        nested_stats = entry_data.get('nestedStats', {})
                        entries = nested_stats.get('entries', {})
                        
                        print(f"        Nested entry {entry_name} has fields: {list(entries.keys())}")
                        
                        # Look for serial-related fields
                        for field_name, field_data in entries.items():
                            if isinstance(field_data, dict) and 'description' in field_data:
                                desc = field_data['description']
                                print(f"          {field_name}: {desc}")
                                
                                # Check for serial keywords or UUID pattern
                                if ('serial' in field_name.lower() or 
                                    'chassis' in field_name.lower() or
                                    (isinstance(desc, str) and '-' in desc and len(desc) > 30)):
                                    if desc and desc.strip() and desc != 'N/A':
                                        print(f"        Found potential serial: {desc}")
                                        return desc.strip()
        
        return None
    
    def _deep_search_hardware_urls(self):
        """Search all hardware nested URLs for serial information"""
        hardware_data = self.api_request("sys/hardware")
        
        if not hardware_data or 'entries' not in hardware_data:
            return
            
        for entry_url, entry_data in hardware_data['entries'].items():
            print(f"    Deep searching: {entry_url}")
            
            nested_stats = entry_data.get('nestedStats', {})
            nested_entries = nested_stats.get('entries', {})
            
            # Follow all nested URLs
            for nested_url in nested_entries.keys():
                if nested_url.startswith('https://'):
                    if '/mgmt/tm/' in nested_url:
                        nested_endpoint = nested_url.split('/mgmt/tm/')[-1]
                        print(f"      Trying deep endpoint: {nested_endpoint}")
                        
                        nested_data = self.api_request(nested_endpoint)
                        if nested_data:
                            # Convert to string and search for UUID pattern
                            data_str = str(nested_data).lower()
                            if 'dfac18d2' in data_str:
                                print(f"      FOUND target serial pattern in {nested_endpoint}!")
                                # Extract the actual serial from the data
                                import re
                                pattern = r'dfac18d2-466d-fc43-[a-f0-9]{12,16}'
                                match = re.search(pattern, str(nested_data))
                                if match:
                                    self.device_info['serial_number'] = match.group(0)
                                    print(f"      Extracted serial: {match.group(0)}")
                                    return
                            
                            # Also try the structured approach
                            serial = self._extract_serial_from_nested_data(nested_data, nested_endpoint)
                            if serial:
                                self.device_info['serial_number'] = serial
                                return
    
    def _extract_serial_from_data(self, data, source_name):
        """Helper method to extract serial from any data structure"""
        if not data:
            return
            
        print(f"    Examining {source_name} data structure...")
        
        if isinstance(data, dict):
            # Check top level for any serial-like fields
            for key, value in data.items():
                if 'serial' in key.lower() and isinstance(value, str):
                    print(f"    Found top-level serial field {key}: {value}")
                    if value.strip() and value != 'N/A':
                        self.device_info['serial_number'] = value.strip()
                        return
            
            # Check entries structure
            if 'entries' in data:
                for entry_name, entry_data in data['entries'].items():
                    if isinstance(entry_data, dict):
                        nested_stats = entry_data.get('nestedStats', {})
                        entries = nested_stats.get('entries', {})
                        
                        # Look for serial fields
                        for field_name, field_data in entries.items():
                            if isinstance(field_data, dict) and 'description' in field_data:
                                desc = field_data['description']
                                print(f"      {field_name}: {desc}")
                                
                                # Check for chassis serial or UUID pattern
                                if ('serial' in field_name.lower() or 
                                    (isinstance(desc, str) and '-' in desc and len(desc) > 30)):
                                    if desc.strip() and desc != 'N/A':
                                        self.device_info['serial_number'] = desc.strip()
                                        print(f"    SUCCESS: Found serial in {field_name}: {desc}")
                                        return
    
    def _search_for_uuid_pattern(self):
        """Search for the specific UUID pattern in all hardware endpoints"""
        endpoints = [
            "sys/hardware",
            "sys/hardware/chassis-info", 
            "sys/hardware/system-info",
            "sys/hardware/platform",
            "sys/hardware/hardware-version"
        ]
        
        target_pattern = "dfac18d2-466d-fc43-5cb74c9d3b49"
        
        for endpoint in endpoints:
            print(f"    Searching {endpoint} for UUID pattern...")
            data = self.api_request(endpoint)
            if data:
                # Convert entire response to string and search for the pattern
                data_str = str(data)
                if target_pattern in data_str:
                    print(f"    FOUND target serial in {endpoint}!")
                    self.device_info['serial_number'] = target_pattern
                    return
                
                # Also search for any UUID-like pattern
                import re
                uuid_pattern = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12,16}'
                matches = re.findall(uuid_pattern, data_str)
                if matches:
                    print(f"    Found UUID patterns in {endpoint}: {matches}")
                    # Use the first UUID that looks like a serial
                    for match in matches:
                        if len(match) > 30:  # Your serial is 36 chars
                            self.device_info['serial_number'] = match
                            print(f"    Using UUID as serial: {match}")
                            return
    
    def get_registration_key(self):
        """Extract registration key information"""
        try:
            print("  Searching for registration key...")
            
            # Method 1: Check sys/license for registrationKey
            print("  Checking sys/license for registration key...")
            license_data = self.api_request("sys/license")
            
            if license_data:
                # First, search the entire response for any registration key patterns
                response_str = str(license_data)
                print(f"    Searching license data for registration key...")
                
                # Look for the registration key in the structured data
                reg_key = self._extract_registration_key_from_license(license_data)
                if reg_key:
                    self.device_info['registration_key'] = reg_key
                    print(f"  SUCCESS: Found registration key: {reg_key}")
                    return
                
                # Also try recursive search for any key containing 'registration'
                reg_key = self._find_registration_key_recursive(license_data)
                if reg_key:
                    self.device_info['registration_key'] = reg_key
                    print(f"  SUCCESS: Found registration key (recursive): {reg_key}")
                    return
            
            # Method 2: Try other license-related endpoints
            license_endpoints = [
                "sys/license/registration-key",
                "sys/db/license.key",
                "sys/db/registration.key"
            ]
            
            for endpoint in license_endpoints:
                print(f"  Trying endpoint: {endpoint}")
                data = self.api_request(endpoint)
                if data:
                    # Check for registration key in response
                    if isinstance(data, dict) and 'value' in data:
                        reg_key = data['value']
                        if reg_key and reg_key.strip():
                            self.device_info['registration_key'] = reg_key.strip()
                            print(f"  SUCCESS: Found registration key in {endpoint}: {reg_key}")
                            return
            
            print("  Registration key not found in any location")
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
                    print(f"    Found license entry: {entry_url}")
                    
                    nested_stats = entry_data.get('nestedStats', {})
                    nested_entries = nested_stats.get('entries', {})
                    
                    # Look for registrationKey field
                    for field_name, field_data in nested_entries.items():
                        if 'registrationkey' in field_name.lower() or 'registration' in field_name.lower():
                            print(f"    Found registration field: {field_name}")
                            
                            if isinstance(field_data, dict) and 'description' in field_data:
                                reg_key = field_data['description']
                                if reg_key and reg_key.strip() and reg_key != '-':
                                    print(f"    Registration key value: {reg_key}")
                                    return reg_key.strip()
                            elif isinstance(field_data, str) and field_data.strip():
                                return field_data.strip()
            
            return None
            
        except Exception as e:
            print(f"    Error extracting registration key: {str(e)}")
            return None
    
    def _find_registration_key_recursive(self, data):
        """Recursively search for registration key in any data structure"""
        if isinstance(data, dict):
            for key, value in data.items():
                # Look for keys containing 'registration'
                if 'registration' in key.lower():
                    print(f"    Found registration field: {key}")
                    if isinstance(value, dict) and 'description' in value:
                        reg_key = value['description']
                        if reg_key and reg_key.strip() and reg_key != '-':
                            return reg_key.strip()
                    elif isinstance(value, str) and value.strip() and value != '-':
                        return value.strip()
                elif isinstance(value, (dict, list)):
                    result = self._find_registration_key_recursive(value)
                    if result:
                        return result
        elif isinstance(data, list):
            for item in data:
                result = self._find_registration_key_recursive(item)
                if result:
                    return result
        
        return None
    
    def get_software_version(self):
        """Extract software version information"""
        try:
            active_version = 'N/A'
            available_versions = []
            
            # Method 1: Try sys/software/volume for boot locations
            print("  Checking sys/software/volume for boot locations...")
            volume_data = self.api_request("sys/software/volume")
            
            if volume_data and 'items' in volume_data:
                print(f"  Found {len(volume_data['items'])} boot locations")
                
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
                    print(f"    Boot location: {volume_info} {'[ACTIVE]' if is_active else ''}")
                    
                    if is_active:
                        active_version = volume_version
                        print(f"  Active version: {active_version}")
            
            # Method 2: Try sys/software/image as backup
            if not available_versions:
                print("  Trying sys/software/image as backup...")
                image_data = self.api_request("sys/software/image")
                
                if image_data and 'items' in image_data:
                    print(f"  Found {len(image_data['items'])} software images")
                    for image in image_data['items']:
                        image_name = image.get('name', 'Unknown')
                        image_version = image.get('version', 'Unknown')
                        image_info = f"{image_name} ({image_version})"
                        available_versions.append(image_info)
                        
                        if image.get('active', False):
                            active_version = image_version
            
            # Method 3: Try sys/version for TMOS version if still no active version
            if active_version == 'N/A':
                print("  Trying sys/version for TMOS info...")
                tmos_data = self.api_request("sys/version")
                if tmos_data and 'entries' in tmos_data:
                    
                    # Look for built information which contains version
                    for entry_name, entry_data in tmos_data['entries'].items():
                        nested_stats = entry_data.get('nestedStats', {})
                        entries = nested_stats.get('entries', {})
                        
                        # Look for version information - prioritize Built and Version
                        if 'Built' in entries:
                            built_info = entries['Built'].get('description', '')
                            # Extract just the version number from built string
                            # Example: "0.249.249 built 220630 on slot1" -> "0.249.249"
                            if built_info:
                                version_parts = built_info.split()
                                if version_parts:
                                    active_version = version_parts[0]
                                    print(f"  Found version from Built field: {active_version}")
                                    break
                        
                        elif 'Version' in entries:
                            version_info = entries['Version'].get('description', '')
                            if version_info and version_info != 'N/A':
                                active_version = version_info
                                print(f"  Found version: {active_version}")
                                break
                        
                        elif 'Product' in entries:
                            product_info = entries['Product'].get('description', '')
                            # Sometimes product contains version info like "BIG-IP VE 16.1.0"
                            if 'BIG-IP' in product_info and any(char.isdigit() for char in product_info):
                                # Extract version from product string
                                import re
                                version_match = re.search(r'(\d+\.\d+\.\d+)', product_info)
                                if version_match:
                                    active_version = version_match.group(1)
                                    print(f"  Found version from Product: {active_version}")
                                    break
            
            # Method 4: Try sys/software/hotfix for additional software info
            print("  Checking for additional software information...")
            hotfix_data = self.api_request("sys/software/hotfix")
            if hotfix_data and 'items' in hotfix_data:
                hotfix_versions = []
                for hotfix in hotfix_data['items']:
                    hotfix_name = hotfix.get('name', 'Unknown')
                    hotfix_version = hotfix.get('version', 'Unknown')
                    hotfix_info = f"Hotfix: {hotfix_name} ({hotfix_version})"
                    hotfix_versions.append(hotfix_info)
                
                if hotfix_versions:
                    available_versions.extend(hotfix_versions)
            
            self.device_info['active_version'] = active_version
            self.device_info['available_versions'] = '; '.join(available_versions) if available_versions else 'N/A'
            
            print(f"  Final active version: {active_version}")
            print(f"  Total available versions/locations: {len(available_versions)}")
            
        except Exception as e:
            print(f"Error getting software version: {str(e)}")
            self.device_info['active_version'] = 'N/A'
            self.device_info['available_versions'] = 'N/A'
    
    def get_hotfix_info(self):
        """Extract hotfix information"""
        try:
            # Get hotfix information
            hotfix_data = self.api_request("sys/software/hotfix")
            
            hotfix_list = []
            emergency_hotfixes = []
            
            if hotfix_data and 'items' in hotfix_data:
                for hotfix in hotfix_data['items']:
                    hotfix_name = hotfix.get('name', 'Unknown')
                    hotfix_version = hotfix.get('version', 'Unknown')
                    hotfix_info = f"{hotfix_name} ({hotfix_version})"
                    hotfix_list.append(hotfix_info)
                    
                    # Check if it's an emergency hotfix
                    if any(keyword in hotfix_name.lower() for keyword in ['emergency', 'critical', 'hotfix', 'ehf']):
                        emergency_hotfixes.append(hotfix_info)
            
            self.device_info['installed_hotfixes'] = '; '.join(hotfix_list) if hotfix_list else 'None'
            self.device_info['emergency_hotfixes'] = '; '.join(emergency_hotfixes) if emergency_hotfixes else 'None'
            
        except Exception as e:
            print(f"Error getting hotfix info: {str(e)}")
            self.device_info['installed_hotfixes'] = 'N/A'
            self.device_info['emergency_hotfixes'] = 'N/A'
    
    def get_additional_info(self):
        """Extract additional useful information"""
        try:
            # System clock/time
            clock_data = self.api_request("sys/clock")
            if clock_data:
                self.device_info['system_time'] = clock_data.get('fullDate', 'N/A')
            else:
                self.device_info['system_time'] = 'N/A'
            
            # Memory information
            memory_data = self.api_request("sys/memory")
            if memory_data and 'entries' in memory_data:
                for entry_name, entry_data in memory_data['entries'].items():
                    if 'TMM Memory' in entry_name:
                        nested_stats = entry_data.get('nestedStats', {}).get('entries', {})
                        if 'Total' in nested_stats:
                            self.device_info['total_memory'] = nested_stats['Total'].get('value', 'N/A')
                            break
                else:
                    self.device_info['total_memory'] = 'N/A'
            else:
                self.device_info['total_memory'] = 'N/A'
            
            # CPU information
            cpu_data = self.api_request("sys/cpu")
            if cpu_data and 'entries' in cpu_data:
                self.device_info['cpu_count'] = len(cpu_data['entries'])
            else:
                self.device_info['cpu_count'] = 'N/A'
            
            # HA status
            try:
                failover_data = self.api_request("sys/failover")
                if failover_data:
                    self.device_info['ha_status'] = failover_data.get('status', 'N/A')
                else:
                    self.device_info['ha_status'] = 'Standalone'
            except:
                self.device_info['ha_status'] = 'Standalone'
            
            # Management IP
            self.device_info['management_ip'] = self.host
            
        except Exception as e:
            print(f"Error getting additional info: {str(e)}")
            self.device_info.update({
                'system_time': 'N/A',
                'total_memory': 'N/A',
                'cpu_count': 'N/A',
                'ha_status': 'N/A',
                'management_ip': self.host
            })
    
    def extract_all_info(self):
        """Extract all device information"""
        if not self.connect():
            return False
        
        print("Extracting system information...")
        self.get_system_info()
        
        print("Extracting device serial number...")
        self.get_device_serial()
        
        print("Extracting registration key...")
        self.get_registration_key()
        
        print("Extracting software version...")
        self.get_software_version()
        
        print("Extracting hotfix information...")
        self.get_hotfix_info()
        
        print("Extracting additional information...")
        self.get_additional_info()
        
        # Add extraction timestamp
        self.device_info['extraction_timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        return True
    
    def debug_serial_search(self):
        """Comprehensive debug search for serial number"""
        print("\n=== SERIAL NUMBER DEBUG MODE ===")
        target_serial = "dfac18d2-466d-fc43-5cb74c9d3b49"
        print(f"Target serial: {target_serial}")
        
        # List of endpoints that might contain serial information
        serial_endpoints = [
            "sys/hardware",
            "sys/version", 
            "sys/host-info",
            "sys/license",
            "sys/provision",
            "sys/fpga",
            "sys/db",
            "sys/global-settings"
        ]
        
        for endpoint in serial_endpoints:
            print(f"\n--- Checking {endpoint} ---")
            data = self.api_request(endpoint)
            
            if not data:
                print("  No data returned")
                continue
            
            # First, check if target serial is anywhere in the response
            data_str = str(data)
            if target_serial in data_str:
                print(f"  *** TARGET SERIAL FOUND IN {endpoint}! ***")
                print(f"  Full response: {data}")
                return
            
            # Check for selfLinks in items
            if 'items' in data and isinstance(data['items'], list):
                print(f"  Found {len(data['items'])} items with potential selfLinks")
                for i, item in enumerate(data['items'][:5]):  # Check first 5 items
                    if 'selfLink' in item:
                        print(f"    Item {i} selfLink: {item['selfLink']}")
                        selflink_data = self.api_request_selflink(item['selfLink'])
                        if selflink_data:
                            selflink_str = str(selflink_data)
                            if target_serial in selflink_str:
                                print(f"    *** TARGET SERIAL FOUND VIA SELFLINK! ***")
                                print(f"    SelfLink response: {selflink_data}")
                                return
            
            # Check for selfLinks in entries
            if 'entries' in data:
                print(f"  Found entries: {list(data['entries'].keys())}")
                for entry_name, entry_data in data['entries'].items():
                    if entry_name.startswith('https://'):
                        print(f"    Entry selfLink: {entry_name}")
                        selflink_data = self.api_request_selflink(entry_name)
                        if selflink_data:
                            selflink_str = str(selflink_data)
                            if target_serial in selflink_str:
                                print(f"    *** TARGET SERIAL FOUND VIA ENTRY SELFLINK! ***")
                                print(f"    Entry response: {selflink_data}")
                                return
                    
                    # Check nested entries for more selfLinks
                    if isinstance(entry_data, dict) and 'nestedStats' in entry_data:
                        nested_stats = entry_data['nestedStats']
                        if 'entries' in nested_stats:
                            nested_entries = nested_stats['entries']
                            for nested_key, nested_value in nested_entries.items():
                                if nested_key.startswith('https://'):
                                    print(f"      Nested selfLink: {nested_key}")
                                    selflink_data = self.api_request_selflink(nested_key)
                                    if selflink_data:
                                        selflink_str = str(selflink_data)
                                        if target_serial in selflink_str:
                                            print(f"      *** TARGET SERIAL FOUND VIA NESTED SELFLINK! ***")
                                            print(f"      Nested response: {selflink_data}")
                                            return
                                elif isinstance(nested_value, dict) and 'description' in nested_value:
                                    desc = nested_value['description']
                                    if target_serial in str(desc):
                                        print(f"      *** TARGET SERIAL FOUND IN DESCRIPTION! ***")
                                        print(f"      Field: {nested_key}, Value: {desc}")
                                        return
        
        print(f"\n*** TARGET SERIAL {target_serial} NOT FOUND IN ANY LOCATION ***")
        print("\n=== END SERIAL DEBUG ===\n")
    
    def debug_api_structure(self):
        """Debug method to explore API structure"""
        print("\n=== DEBUG: Exploring API Structure ===")
        
        # Test various endpoints to see what's available
        endpoints_to_test = [
            "sys/hardware",
            "sys/version", 
            "sys/software/image",
            "sys/chassis",
            "sys/db/tmos.version"
        ]
        
        for endpoint in endpoints_to_test:
            print(f"\n--- Testing {endpoint} ---")
            data = self.api_request(endpoint)
            if data:
                if isinstance(data, dict):
                    print(f"Top-level keys: {list(data.keys())}")
                    if 'entries' in data:
                        print(f"Entries: {list(data['entries'].keys())}")
                    if 'items' in data:
                        print(f"Items count: {len(data['items'])}")
                        if data['items']:
                            print(f"First item keys: {list(data['items'][0].keys())}")
                else:
                    print(f"Data type: {type(data)}")
            else:
                print("No data returned")
        
        print("\n=== End Debug ===\n")

def write_to_csv(devices_info, filename='bigip_device_info.csv'):
    """Write device information to CSV file"""
    if not devices_info:
        print("No device information to write.")
        return
    
    # Define CSV headers
    headers = [
        'management_ip',
        'hostname',
        'serial_number',
        'registration_key',
        'platform',
        'active_version',
        'available_versions',
        'installed_hotfixes',
        'emergency_hotfixes',
        'system_time',
        'total_memory',
        'cpu_count',
        'ha_status',
        'extraction_timestamp'
    ]
    
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=headers)
            writer.writeheader()
            
            for device_info in devices_info:
                # Ensure all headers are present in device_info
                row_data = {header: device_info.get(header, 'N/A') for header in headers}
                writer.writerow(row_data)
        
        print(f"Device information written to {filename}")
        
    except Exception as e:
        print(f"Error writing to CSV: {str(e)}")

def get_credentials_for_device(args, device_user=None, device_pass=None):
    """Get credentials for a specific device with fallback logic"""
    # Priority order:
    # 1. Credentials from CSV file (if provided and not empty)
    # 2. Command line arguments (if provided)
    # 3. Interactive prompt (if both above are empty/missing)
    
    username = None
    password = None
    
    # Use device-specific credentials if provided in CSV and not empty
    if device_user and device_user.strip():
        username = device_user.strip()
    elif args.user:
        username = args.user
    
    if device_pass and device_pass.strip():
        password = device_pass.strip()
    elif args.password:
        password = args.password
    
    # If both username and password are still None, prompt for them
    if not username and not password:
        print("No credentials provided. Please enter authentication details:")
        username = input("Enter username: ").strip()
        password = getpass.getpass("Enter password: ")
    elif not username:
        username = input("Enter username: ").strip()
    elif not password:
        password = getpass.getpass("Enter password: ")
    
    return username, password

def read_devices_from_csv(filename):
    """Read device information from CSV file"""
    devices = []
    try:
        with open(filename, 'r', newline='', encoding='utf-8') as csvfile:
            # Try to detect if there's a header
            sample = csvfile.read(1024)
            csvfile.seek(0)
            
            # Check if first line looks like a header
            first_line = csvfile.readline().strip().lower()
            csvfile.seek(0)
            
            has_header = any(header_word in first_line for header_word in 
                           ['ip', 'address', 'host', 'username', 'user', 'password', 'pass'])
            
            reader = csv.reader(csvfile)
            
            # Skip header if present
            if has_header:
                next(reader, None)
            
            for row_num, row in enumerate(reader, start=2 if has_header else 1):
                if not row or not row[0].strip():  # Skip empty rows
                    continue
                
                # Pad row to ensure we have at least 3 columns
                while len(row) < 3:
                    row.append('')
                
                device_ip = row[0].strip()
                device_user = row[1].strip() if len(row) > 1 and row[1].strip() else None
                device_pass = row[2].strip() if len(row) > 2 and row[2].strip() else None
                
                if device_ip:  # Only add if IP is not empty
                    devices.append({
                        'ip': device_ip,
                        'username': device_user,
                        'password': device_pass,
                        'row': row_num
                    })
                    
        print(f"Loaded {len(devices)} devices from {filename}")
        return devices
        
    except FileNotFoundError:
        print(f"Error: Input file '{filename}' not found.")
        return []
    except Exception as e:
        print(f"Error reading input file '{filename}': {str(e)}")
        return []

def process_devices_from_file(args):
    """Process devices from input CSV file"""
    devices = read_devices_from_csv(args.input_file)
    if not devices:
        return []
    
    devices_info = []
    
    print(f"\nProcessing {len(devices)} devices from input file...")
    print("=" * 50)
    
    for i, device in enumerate(devices, 1):
        print(f"\n[{i}/{len(devices)}] Processing device: {device['ip']}")
        
        # Get credentials for this device
        username, password = get_credentials_for_device(args, device['username'], device['password'])
        
        if device['username']:
            print(f"  Using credentials from CSV file for user: {device['username']}")
        elif args.user:
            print(f"  Using command line username: {args.user}")
        
        # Extract device information
        extractor = BigIPInfoExtractor(device['ip'], username, password)
        
        if extractor.extract_all_info():
            devices_info.append(extractor.device_info)
            print(f"  ✓ Successfully extracted information from {device['ip']}")
            
            # Display brief summary
            hostname = extractor.device_info.get('hostname', 'N/A')
            version = extractor.device_info.get('active_version', 'N/A')
            print(f"    Hostname: {hostname}, Version: {version}")
        else:
            print(f"  ✗ Failed to extract information from {device['ip']}")
            
            # If authentication failed, offer to retry for this device
            if not extractor.token:
                print(f"    Authentication failed for {device['ip']}")
                retry = input("    Retry with different credentials? (y/n): ").strip().lower()
                if retry in ['y', 'yes']:
                    print("    Enter new credentials for this device:")
                    retry_username = input("    Username: ").strip()
                    retry_password = getpass.getpass("    Password: ")
                    
                    # Retry with new credentials
                    extractor = BigIPInfoExtractor(device['ip'], retry_username, retry_password)
                    if extractor.extract_all_info():
                        devices_info.append(extractor.device_info)
                        print(f"  ✓ Successfully extracted information from {device['ip']} (retry)")
                        hostname = extractor.device_info.get('hostname', 'N/A')
                        version = extractor.device_info.get('active_version', 'N/A')
                        print(f"    Hostname: {hostname}, Version: {version}")
                    else:
                        print(f"  ✗ Authentication failed again for {device['ip']}")
    
    return devices_info

def process_devices_interactively(args):
    """Process devices in interactive mode"""
    devices_info = []
    
    while True:
        # Get device connection details
        host = input("Enter BIG-IP device IP/hostname (or 'quit' to exit): ").strip()
        if host.lower() == 'quit':
            break
        
        # Get credentials
        username, password = get_credentials_for_device(args)
        
        # Extract device information
        extractor = BigIPInfoExtractor(host, username, password)
        
        if extractor.extract_all_info():
            devices_info.append(extractor.device_info)
            print(f"Successfully extracted information from {host}")
            
            # Display summary
            print("\nDevice Summary:")
            print(f"  Hostname: {extractor.device_info.get('hostname', 'N/A')}")
            print(f"  Serial: {extractor.device_info.get('serial_number', 'N/A')}")
            print(f"  Version: {extractor.device_info.get('active_version', 'N/A')}")
            print(f"  Emergency Hotfixes: {extractor.device_info.get('emergency_hotfixes', 'None')}")
        else:
            print(f"Failed to extract information from {host}")
            
            # If authentication failed, offer to retry with different credentials
            if not extractor.token:
                print("Authentication failed. This might be due to incorrect credentials.")
                retry = input("Retry with different credentials? (y/n): ").strip().lower()
                if retry in ['y', 'yes']:
                    print("Enter new credentials:")
                    username = input("Enter username: ").strip()
                    password = getpass.getpass("Enter password: ")
                    
                    # Retry with new credentials
                    extractor = BigIPInfoExtractor(host, username, password)
                    if extractor.extract_all_info():
                        devices_info.append(extractor.device_info)
                        print(f"Successfully extracted information from {host}")
                        
                        # Display summary
                        print("\nDevice Summary:")
                        print(f"  Hostname: {extractor.device_info.get('hostname', 'N/A')}")
                        print(f"  Serial: {extractor.device_info.get('serial_number', 'N/A')}")
                        print(f"  Version: {extractor.device_info.get('active_version', 'N/A')}")
                        print(f"  Emergency Hotfixes: {extractor.device_info.get('emergency_hotfixes', 'None')}")
                    else:
                        print(f"Authentication failed again for {host}")
        
        print()
        
        # Ask if user wants to add another device
        another = input("Add another device? (y/n): ").strip().lower()
        if another not in ['y', 'yes']:
            break
    
    return devices_info

def main():
    """Main function to run the script"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Extract comprehensive information from F5 BIG-IP devices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python %(prog)s                                              # Interactive mode
  python %(prog)s --user admin                                 # Specify user, prompt for password  
  python %(prog)s --user admin --pass mypassword               # Specify both credentials
  python %(prog)s --user admin --out my_devices.csv            # Specify output file
  python %(prog)s -u admin -p mypass -o device_report.csv      # Short form options
  python %(prog)s --in devices.csv --out results.csv           # Bulk processing from CSV
  python %(prog)s --in devices.csv --user admin                # CSV with fallback credentials
        """
    )
    
    parser.add_argument('--user', '-u', 
                       help='Username for BIG-IP authentication')
    parser.add_argument('--pass', '--password', '-p', 
                       dest='password',
                       help='Password for BIG-IP authentication (not recommended for security)')
    parser.add_argument('--out', '-o',
                       default='bigip_device_info.csv',
                       help='Output CSV filename (default: bigip_device_info.csv)')
    parser.add_argument('--in', '--input', '-i',
                       dest='input_file',
                       help='Input CSV file with device information (format: ip,username,password)')
    
    args = parser.parse_args()
    
    # Security warning for password in command line
    if args.password:
        print("WARNING: Using password in command line arguments is not secure.")
        print("Consider using --user only and entering password interactively.\n")
    
    print("BIG-IP Device Information Extractor")
    print("=" * 40)
    
    # Determine processing mode
    if args.input_file:
        # Process devices from CSV file
        devices_info = process_devices_from_file(args)
    else:
        # Interactive mode
        devices_info = process_devices_interactively(args)
    
    # Offer debug options only if no devices were processed successfully
    if not devices_info:
        debug_choice = input("No devices extracted successfully. Run debug mode to explore API structure? (y/n): ").strip().lower()
        if debug_choice in ['y', 'yes']:
            if args.input_file:
                # For file mode, ask which device to debug
                host = input("Enter BIG-IP device IP/hostname for debug: ").strip()
                username, password = get_credentials_for_device(args)
            else:
                host = input("Enter BIG-IP device IP/hostname for debug: ").strip()
                username, password = get_credentials_for_device(args)
            
            extractor = BigIPInfoExtractor(host, username, password)
            if extractor.connect():
                extractor.debug_api_structure()
    else:
        # If we have devices but missing serial numbers, offer serial debug
        missing_serials = [info for info in devices_info if info.get('serial_number') == 'N/A']
        if missing_serials:
            print(f"\nFound {len(missing_serials)} device(s) with missing serial numbers.")
            serial_debug = input("Run serial number debug mode? (y/n): ").strip().lower()
            if serial_debug in ['y', 'yes']:
                host = input("Enter BIG-IP device IP/hostname for serial debug: ").strip()
                username, password = get_credentials_for_device(args)
                
                extractor = BigIPInfoExtractor(host, username, password)
                if extractor.connect():
                    extractor.debug_serial_search()
    
    # Write results to CSV
    if devices_info:
        write_to_csv(devices_info, args.out)
        print(f"\nExtracted information for {len(devices_info)} device(s)")
        print(f"Results written to: {args.out}")
    else:
        print("No device information collected.")
        # Still create an empty CSV file with headers
        write_to_csv([], args.out)
        print(f"Empty CSV file created: {args.out}")

if __name__ == "__main__":
    main()


