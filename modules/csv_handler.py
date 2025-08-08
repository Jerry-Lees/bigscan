"""
CSV file handling utilities for reading and writing device information
"""

import csv


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
        'memory_used',
        'tmm_memory',
        'cpu_count',
        'ha_status',
        'qkview_downloaded',
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
