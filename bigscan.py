#!/usr/bin/env python3
"""
BIG-IP Device Information Extractor

This script connects to F5 BIG-IP devices and extracts comprehensive system information
including hostname, serial number, registration key, software version, hotfixes, and more.
The data is exported to a CSV file for easy analysis.

Enhanced QKView Feature:
- Uses F5's official autodeploy endpoint for reliable QKView generation
- Proper asynchronous task monitoring
- Downloads QKViews to local 'qkviews' directory
- Automatic cleanup of remote files after download
- Enhanced error handling and progress reporting

Requirements:
    pip install requests urllib3

Usage:
    python bigscan.py [--user USERNAME] [--pass PASSWORD] [--out FILENAME] [--in INPUT_CSV] [--qkview] [--help]
    
Examples:
    python bigscan.py                                              # Interactive mode
    python bigscan.py --user admin                                 # Specify user, prompt for password  
    python bigscan.py --user admin --pass mypassword               # Specify both credentials
    python bigscan.py --user admin --out my_devices.csv            # Specify output file
    python bigscan.py -u admin -p mypass -o device_report.csv      # Short form options
    python bigscan.py --in devices.csv --out results.csv           # Bulk processing from CSV
    python bigscan.py --in devices.csv --user admin                # CSV with fallback credentials
    python bigscan.py --in devices.csv --qkview --out results.csv  # Include QKView creation
    python bigscan.py -q --qkview-timeout 1200 --in devices.csv    # QKView with 20min timeout
"""

import csv
import json
import sys
import getpass
import argparse
import os
import time
from datetime import datetime
import requests
import urllib3

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class BigIPInfoExtractor:
    def __init__(self, host, username, password, create_qkview=False, qkview_timeout=1200):
        """Initialize connection to BIG-IP device"""
        self.host = host
        self.username = username
        self.password = password
        self.token = None
        self.session = requests.Session()
        self.session.verify = False
        self.base_url = f"https://{self.host}"
        self.device_info = {}
        self.create_qkview = create_qkview
        self.qkview_timeout = qkview_timeout
        self.token_timeout = 1200  # 20 minutes default token timeout
        
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
                    # Extend token timeout for long operations
                    self._extend_token_timeout()
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
    
    def _extend_token_timeout(self):
        """Extend the authentication token timeout"""
        try:
            if not self.token:
                return
            
            extend_url = f"{self.base_url}/mgmt/shared/authz/tokens/{self.token}"
            extend_payload = {
                "timeout": self.token_timeout
            }
            
            response = self.session.patch(extend_url, json=extend_payload, timeout=30)
            response.raise_for_status()
            
        except Exception as e:
            print(f"Warning: Could not extend token timeout for {self.host}: {str(e)}")
    
    def logout(self):
        """Logout and invalidate the authentication token"""
        try:
            if not self.token:
                return
            
            logout_url = f"{self.base_url}/mgmt/shared/authz/tokens/{self.token}"
            self.session.delete(logout_url, timeout=30)
            
            # Clean up session
            self.token = None
            if 'X-F5-Auth-Token' in self.session.headers:
                del self.session.headers['X-F5-Auth-Token']
            
        except Exception as e:
            print(f"Warning: Could not logout cleanly from {self.host}: {str(e)}")
    
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
        return self.get_auth_token()
    
    def create_and_download_qkview(self):
        """Create QKView on remote device and download it using enhanced F5 autodeploy endpoint"""
        try:
            print("  Creating QKView using F5 autodeploy endpoint...")
            print(f"  QKView timeout configured for: {self.qkview_timeout} seconds ({self.qkview_timeout/60:.1f} minutes)")
            
            # Step 1: Create QKView task
            task_id = self._create_qkview_task()
            if not task_id:
                print("  ✗ Failed to create QKView task")
                return False
            
            # Step 2: Wait for QKView to complete
            qkview_info = self._wait_for_qkview_completion(task_id)
            if not qkview_info:
                print("  ✗ QKView creation timed out or failed")
                return False
            
            # Step 3: Download QKView
            download_result, downloaded_file_size = self._download_qkview(qkview_info)
            if download_result:
                print(f"  ✓ QKView downloaded successfully")
                
                # Step 4: Cleanup only after successful download verification
                filename = qkview_info.get('name')
                if filename and downloaded_file_size > 5 * 1024 * 1024:  # Only cleanup if > 5MB
                    print(f"  Cleaning up remote files after successful download verification...")
                    self._cleanup_qkview_file(filename)
                    self._cleanup_qkview_task(task_id)
                elif filename:
                    print(f"  ⚠ Skipping cleanup due to small file size - may indicate incomplete download")
                
                return True
            else:
                print("  ✗ Failed to download QKView")
                # Don't cleanup if download failed - leave files for debugging
                print(f"  ℹ Leaving remote files for debugging since download failed")
                return False
                
        except Exception as e:
            print(f"  ✗ Error creating/downloading QKView: {str(e)}")
            import traceback
            print(f"  Traceback: {traceback.format_exc()}")
            return False
    
    def _create_qkview_task(self):
        """Create QKView task using F5 autodeploy endpoint"""
        try:
            # Generate a unique QKView name with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            hostname = self.device_info.get('hostname', self.host)
            
            # Clean hostname for filename (remove special characters)
            import re
            clean_hostname = re.sub(r'[^\w\-_\.]', '_', hostname)
            
            # IMPORTANT: Only provide the filename, not a path!
            # F5 will automatically place it in /var/tmp/
            qkview_name = f"{clean_hostname}_{timestamp}.qkview"
            
            # Use the F5 autodeploy endpoint
            qkview_url = f"{self.base_url}/mgmt/cm/autodeploy/qkview"
            
            # Payload according to F5 documentation - just the filename
            qkview_payload = {"name": qkview_name}
            
            print(f"    Creating QKView task: {qkview_name}")
            print(f"    F5 will save to: /var/tmp/{qkview_name}")
            print(f"    Payload being sent: {json.dumps(qkview_payload)}")
            
            # Submit QKView creation request (asynchronous)
            try:
                print(f"    Sending POST to: {qkview_url}")
                response = self.session.post(
                    qkview_url,
                    json=qkview_payload,
                    timeout=30  # Quick timeout for task creation
                )
                print(f"    Response status: {response.status_code}")
                
            except requests.exceptions.Timeout:
                print(f"    ✗ QKView task creation timed out")
                return None
            except Exception as e:
                print(f"    ✗ QKView task creation failed: {str(e)}")
                return None
            
            if response.status_code in [200, 202]:
                try:
                    response_data = response.json()
                    print(f"    Raw response: {json.dumps(response_data, indent=2)}")
                except:
                    response_data = {}
                
                # Extract the task ID from the response
                task_id = response_data.get('id')
                if task_id:
                    print(f"    QKView task created with ID: {task_id}")
                    return task_id
                else:
                    print(f"    ✗ No task ID found in response")
                    print(f"    Response: {response_data}")
                    return None
                    
            else:
                print(f"    ✗ Failed to create QKView task: {response.status_code}")
                try:
                    error_details = response.json()
                    print(f"    Error details: {error_details}")
                except:
                    print(f"    Response text: {response.text[:200]}")
                
                # Try with a simpler filename if the original failed
                if 'invalid' in response.text.lower() or 'name' in response.text.lower():
                    print(f"    Trying with simplified filename...")
                    simple_name = f"qkview_{timestamp}.qkview"
                    simple_payload = {"name": simple_name}
                    print(f"    Simplified name: {simple_name}")
                    
                    retry_response = self.session.post(qkview_url, json=simple_payload, timeout=30)
                    if retry_response.status_code in [200, 202]:
                        retry_data = retry_response.json()
                        task_id = retry_data.get('id')
                        if task_id:
                            print(f"    QKView task created with simplified name: {simple_name}")
                            print(f"    Task ID: {task_id}")
                            return task_id
                
                return None
                
        except Exception as e:
            print(f"    ✗ Error creating QKView task: {str(e)}")
            return None
    
    def _wait_for_qkview_completion(self, task_id):
        """Wait for QKView task completion using F5 autodeploy endpoint"""
        try:
            print(f"    Waiting for QKView task completion...")
            print(f"      Status check for task {task_id}")
            
            status_url = f"{self.base_url}/mgmt/cm/autodeploy/qkview/{task_id}"
            start_time = time.time()
            check_interval = 15  # Check every 15 seconds
            check_count = 0
            spinner_chars = ['/', '-', '\\', '|']
            spinner_index = 0
            current_status = 'Unknown'
            current_generation = 'N/A'
            
            while (time.time() - start_time) < self.qkview_timeout:
                check_count += 1
                elapsed = int(time.time() - start_time)
                
                try:
                    response = self.session.get(status_url, timeout=30)
                    response.raise_for_status()
                    
                    result = response.json()
                    current_status = result.get('status', 'Unknown')
                    current_generation = result.get('generation', 'N/A')
                    
                    if current_status == 'SUCCEEDED':
                        print(f'\r      [{elapsed}s] Task Status (Generation: {current_generation}): {current_status} : Completed!                              ')
                        print(f'    ✓ QKView generation completed successfully (after {elapsed}s)')
                        return result
                    
                    elif current_status == 'FAILED':
                        print(f'\r      [{elapsed}s] Task Status (Generation: {current_generation}): {current_status} : Failed!                              ')
                        print(f'    ✗ QKView generation failed (after {elapsed}s)')
                        return None
                    
                    elif current_status == 'IN_PROGRESS':
                        # Show spinning progress indicator with countdown
                        for i in range(check_interval):
                            spinner = spinner_chars[spinner_index % len(spinner_chars)]
                            remaining = check_interval - i
                            print(f'\r      [{elapsed + i}s] Task Status (Generation: {current_generation}): {current_status} : Waiting {remaining} seconds before next check... {spinner}  ', end='', flush=True)
                            spinner_index += 1
                            time.sleep(1)
                    else:
                        print(f'\r      [{elapsed}s] Task Status (Generation: {current_generation}): {current_status} : Unknown status                              ')
                        time.sleep(check_interval)
                
                except requests.exceptions.RequestException as e:
                    print(f'\r      [{elapsed}s] Task Status (Generation: {current_generation}): ERROR : Connection failed (attempt {check_count})                              ')
                    if check_count >= 3:
                        print(f'\n    ✗ Multiple consecutive failures, aborting')
                        return None
                    time.sleep(check_interval)
            
            elapsed = int(time.time() - start_time)
            print(f'\r      [{elapsed}s] Task Status (Generation: {current_generation}): TIMEOUT : Exceeded {self.qkview_timeout}s limit                              ')
            print(f'\n    ✗ QKView creation timed out after {elapsed} seconds')
            return None
            
        except Exception as e:
            elapsed = int(time.time() - start_time) if 'start_time' in locals() else 0
            print(f'\r      [{elapsed}s] Task Status (Generation: N/A): ERROR : {str(e)}                              ')
            print(f'\n    ✗ Error waiting for QKView completion')
            return None
    
    def _download_qkview(self, qkview_info):
        """Download QKView file from the BIG-IP device"""
        try:
            # Extract filename from qkview_info
            filename = qkview_info.get('name')
            if not filename:
                print(f"    ✗ No filename found in QKView info")
                return False, 0
            
            print(f"    Downloading QKView: {filename}")
            
            # First, let's find where the QKView file actually is
            actual_path = self._find_qkview_file(filename)
            if actual_path:
                print(f"    Found QKView at: {actual_path}")
            else:
                print(f"    Warning: Could not locate QKView file on remote system")
            
            # Try multiple download methods in order of reliability
            download_methods = [
                self._download_via_autodeploy_uri,  # Try F5 official method first
                self._download_via_file_transfer,
                self._download_via_bash_copy
            ]
            
            for method in download_methods:
                method_name = method.__name__.replace('_', '_')  # Keep underscores as-is
                print(f"    Attempting download method: {method_name}")
                try:
                    result = method(qkview_info, filename, actual_path)
                    if isinstance(result, tuple):
                        success, file_size = result
                        if success:
                            print(f"    ✓ Download successful using {method_name}")
                            return True, file_size
                        else:
                            print(f"    ✗ Download failed using {method_name}")
                    elif result:
                        # Legacy method that returns boolean only
                        print(f"    ✓ Download successful using {method_name} (legacy)")
                        return True, 0
                    else:
                        print(f"    ✗ Download failed using {method_name} (legacy)")
                except Exception as e:
                    print(f"    ✗ Exception in {method_name}: {str(e)}")
                    continue
            
            print(f"    ✗ All download methods failed")
            return False, 0
                
        except Exception as e:
            print(f"    ✗ Error downloading QKView: {str(e)}")
            return False, 0
    
    def _find_qkview_file(self, filename):
        """Find the actual location of the QKView file on the BIG-IP"""
        try:
            print(f"    Searching for QKView file...")
            bash_url = f"{self.base_url}/mgmt/tm/util/bash"
            
            # Common locations where QKView files might be stored
            search_locations = [
                f"/var/tmp/{filename}",
                f"/shared/support/{filename}",
                f"/var/core/{filename}", 
                f"/shared/core/{filename}",
                f"/var/log/{filename}",
                f"/shared/images/{filename}"
            ]
            
            # Also try to find any QKView files with similar names
            search_patterns = [
                f"/var/tmp/*{filename[-20:]}*",  # Last 20 chars of filename
                "/var/tmp/*.qkview",
                "/shared/support/*.qkview",
                "/var/core/*.qkview"
            ]
            
            # Search in specific locations first
            for location in search_locations:
                find_payload = {
                    "command": "run",
                    "utilCmdArgs": f"-c 'ls -la {location} 2>/dev/null || echo \"NOT_FOUND\"'"
                }
                
                response = self.session.post(bash_url, json=find_payload, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    if 'commandResult' in result:
                        command_result = result['commandResult'].strip()
                        if 'NOT_FOUND' not in command_result and command_result:
                            print(f"      Found file: {command_result}")
                            return location
            
            # Search with patterns if exact location not found
            for pattern in search_patterns:
                find_payload = {
                    "command": "run",
                    "utilCmdArgs": f"-c 'ls -la {pattern} 2>/dev/null | head -5'"
                }
                
                response = self.session.post(bash_url, json=find_payload, timeout=30)
                if response.status_code == 200:
                    result = response.json()
                    if 'commandResult' in result:
                        command_result = result['commandResult'].strip()
                        if command_result and 'No such file' not in command_result:
                            print(f"      Pattern search results: {command_result}")
                            # Try to extract the actual file path
                            lines = command_result.split('\n')
                            for line in lines:
                                if '.qkview' in line and filename in line:
                                    # Extract full path from ls output
                                    parts = line.split()
                                    if len(parts) >= 9:
                                        # Last part should be the filename/path
                                        found_path = parts[-1]
                                        if found_path.startswith('/'):
                                            return found_path
            
            return None
            
        except Exception as e:
            print(f"      Error searching for QKView file: {str(e)}")
            return None
    
    def _download_via_autodeploy_uri(self, qkview_info, filename, actual_path=None):
        """Download using the qkviewUri from autodeploy response with F5's official chunked method"""
        try:
            qkview_uri = qkview_info.get('qkviewUri')
            if not qkview_uri:
                print(f"      No qkviewUri found in response")
                return False, 0
            
            print(f"      Using F5 official chunked download method")
            print(f"      Autodeploy URI: {qkview_uri}")
            
            # Handle localhost replacement in URI
            if 'localhost' in qkview_uri:
                download_url = qkview_uri.replace('localhost', self.host)
            elif qkview_uri.startswith('https://'):
                download_url = qkview_uri
            else:
                download_url = f"https://{self.host}{qkview_uri}"
            
            print(f"      Download URL: {download_url}")
            
            return self._download_chunked_f5_method(download_url, filename)
            
        except Exception as e:
            print(f"      Autodeploy URI method failed: {str(e)}")
            return False, 0
    
    def _download_chunked_f5_method(self, download_url, filename):
        """Download using F5's official chunked method from KB article K04396542"""
        try:
            local_dir = "QKViews"
            local_path = os.path.join(local_dir, filename)
            
            chunk_size = 512 * 1024  # 512KB chunks as per F5 documentation
            
            # Create download session with same authentication
            download_session = requests.Session()
            download_session.verify = False
            
            if self.token:
                download_session.headers.update({
                    'X-F5-Auth-Token': self.token
                })
            
            print(f"      Starting F5 chunked download: {filename}")
            print(f"      Chunk size: {chunk_size / 1024:.0f}KB")
            
            with open(local_path, 'wb') as f:
                start = 0
                end = chunk_size - 1
                size = 0
                current_bytes = 0
                chunk_count = 0
                total_chunks = 0
                
                while True:
                    chunk_count += 1
                    content_range = f"{start}-{end}/{size}"
                    
                    headers = {
                        'Content-Type': 'application/octet-stream',
                        'Content-Range': content_range
                    }
                    
                    try:
                        resp = download_session.get(
                            download_url,
                            headers=headers,
                            timeout=self.qkview_timeout,
                            stream=True
                        )
                    except Exception as e:
                        print(f"\r        Chunk {chunk_count} request failed: {str(e)}")
                        return False, 0
                    
                    if resp.status_code == 200:
                        # If the size is zero, this is the first time through the loop
                        # and we need to figure out the total size of the file
                        if size > 0:
                            current_bytes += chunk_size
                            for chunk in resp.iter_content(chunk_size=8192):
                                f.write(chunk)
                            
                            # Calculate and show progress on same line
                            progress = (current_bytes / size) * 100
                            chunk_display = f"(Chunk {chunk_count}/{total_chunks})" if total_chunks > 0 else f"(Chunk {chunk_count})"
                            print(f"\r        Progress: {progress:.1f}% ({current_bytes / (1024*1024):.1f} MB / {size / (1024*1024):.1f} MB) {chunk_display}", end='', flush=True)
                        
                        # Once we've downloaded the entire file, break out of the loop
                        if end == size:
                            print(f"\n        Download complete!")
                            break
                        
                        # Get the Content-Range header to determine total file size
                        crange = resp.headers.get('Content-Range', '')
                        
                        # Determine the total number of bytes to read
                        if size == 0:
                            try:
                                size = int(crange.split('/')[-1]) - 1
                                total_chunks = (size // chunk_size) + (1 if size % chunk_size else 0)
                                print(f"        Total file size determined: {size / (1024*1024):.1f} MB ({total_chunks} chunks)")
                                
                                # If the file is smaller than the chunk size, adjust
                                if chunk_size > size:
                                    end = size
                                    continue
                            except (ValueError, IndexError):
                                print(f"\r        Could not determine file size from Content-Range: {crange}")
                                return False, 0
                        
                        # Calculate next chunk range
                        start += chunk_size
                        if (current_bytes + chunk_size) > size:
                            end = size
                        else:
                            end = start + chunk_size - 1
                            
                    elif resp.status_code == 206:  # Partial Content
                        # Handle 206 response similar to 200
                        if size > 0:
                            current_bytes += chunk_size
                            for chunk in resp.iter_content(chunk_size=8192):
                                f.write(chunk)
                            
                            # Show progress
                            progress = (current_bytes / size) * 100
                            chunk_display = f"(Chunk {chunk_count}/{total_chunks})" if total_chunks > 0 else f"(Chunk {chunk_count})"
                            print(f"\r        Progress: {progress:.1f}% ({current_bytes / (1024*1024):.1f} MB / {size / (1024*1024):.1f} MB) {chunk_display}", end='', flush=True)
                        
                        if end == size:
                            print(f"\n        Download complete!")
                            break
                            
                        # Get total size from 206 response
                        crange = resp.headers.get('Content-Range', '')
                        if size == 0:
                            try:
                                size = int(crange.split('/')[-1]) - 1
                                total_chunks = (size // chunk_size) + (1 if size % chunk_size else 0)
                                print(f"        Total file size from 206: {size / (1024*1024):.1f} MB ({total_chunks} chunks)")
                            except (ValueError, IndexError):
                                print(f"\r        Could not determine file size from 206 Content-Range: {crange}")
                                return False, 0
                        
                        start += chunk_size
                        if (current_bytes + chunk_size) > size:
                            end = size
                        else:
                            end = start + chunk_size - 1
                            
                    elif resp.status_code == 400 and end >= size:
                        # HTTP 400 on final chunk often happens when requesting beyond file end
                        # This is normal behavior for some F5 versions - check if we have the complete file
                        print(f"\r        Got HTTP 400 on final chunk - checking if download is complete...")
                        
                        # Check if we've downloaded the expected amount
                        current_file_size = f.tell() if hasattr(f, 'tell') else 0
                        if current_file_size > 0 and size > 0:
                            if abs(current_file_size - (size + 1)) <= 1024:  # Allow 1KB tolerance
                                print(f"\n        Download appears complete despite HTTP 400 (got {current_file_size} bytes)")
                                break
                        
                        # If we're very close to the end, consider it successful
                        if end >= size * 0.99:  # Within 1% of completion
                            print(f"\n        Download {end/size*100:.1f}% complete - treating as successful")
                            break
                        
                        print(f"\r        Unexpected response code: {resp.status_code} (chunk {chunk_count})")
                        return False, 0
                            
                    else:
                        print(f"\r        Unexpected response code: {resp.status_code} (chunk {chunk_count})")
                        
                        # Check if this is happening near the end - might still be successful
                        if end >= size * 0.95:  # Within 5% of completion
                            print(f"\n        Download {end/size*100:.1f}% complete - checking file integrity...")
                            break
                        
                        return False, 0
            
            final_size = os.path.getsize(local_path)
            print(f"\n      ✓ F5 chunked download completed: {filename}")
            print(f"      Final file size: {final_size / (1024*1024):.1f} MB")
            
            # Verify file size matches expected (with tolerance for F5's chunked method)
            if size > 0:
                expected_size = size + 1  # Size is 0-based, so add 1 for actual bytes
                size_difference = abs(final_size - expected_size)
                tolerance = max(1024, expected_size * 0.01)  # 1KB or 1% tolerance, whichever is larger
                
                if size_difference <= tolerance:
                    print(f"      ✓ File size verified: {final_size / (1024*1024):.1f} MB (within tolerance)")
                else:
                    print(f"      ⚠ Warning: File size mismatch. Expected: {expected_size / (1024*1024):.1f} MB, Downloaded: {final_size / (1024*1024):.1f} MB")
                    # Don't fail if we got a reasonable file size - some F5 versions have chunking quirks
                    if final_size >= expected_size * 0.95:  # At least 95% of expected size
                        print(f"      ✓ File size is acceptable (95%+ of expected)")
                    else:
                        return False, final_size
            
            # Verify we got a reasonable file size for a QKView
            if final_size < 1024 * 1024:  # Less than 1MB is suspicious for a QKView
                print(f"      ⚠ Warning: File seems very small for a QKView ({final_size / (1024*1024):.1f} MB)")
                
                # Check if it's an error response
                try:
                    with open(local_path, 'rb') as f:
                        first_bytes = f.read(100)
                        if b'<html>' in first_bytes.lower() or b'error' in first_bytes.lower():
                            print(f"      ✗ File appears to be an error response")
                            return False, final_size
                except:
                    pass
                
                # If it's very small but looks like binary data, warn but don't fail
                print(f"      ⚠ Proceeding despite small size - may be a minimal QKView")
            
            return True, final_size
            
        except Exception as e:
            print(f"\n      F5 chunked download failed: {str(e)}")
            return False, 0
    
    def _download_via_file_transfer(self, qkview_info, filename, actual_path=None):
        """Download via F5 file transfer API after moving file"""
        try:
            source_path = actual_path or f"/var/tmp/{filename}"
            print(f"      Moving QKView from {source_path} to download directory...")
            
            # Use unix-mv to move the file to the download directory
            move_url = f"{self.base_url}/mgmt/tm/util/unix-mv"
            move_payload = {
                "command": "run",
                "utilCmdArgs": f"{source_path} /var/config/rest/downloads/{filename}"
            }
            
            response = self.session.post(move_url, json=move_payload, timeout=60)
            if response.status_code != 200:
                print(f"      Move operation failed: {response.status_code}")
                
                # Check if the response gives us more details
                try:
                    result = response.json()
                    if 'message' in result:
                        print(f"      Error details: {result['message']}")
                except:
                    pass
                
                # Try using bash as fallback for move operation
                print(f"      Trying bash move command...")
                bash_url = f"{self.base_url}/mgmt/tm/util/bash"
                bash_payload = {
                    "command": "run", 
                    "utilCmdArgs": f"-c 'mv \"{source_path}\" \"/var/config/rest/downloads/{filename}\"'"
                }
                
                bash_response = self.session.post(bash_url, json=bash_payload, timeout=60)
                if bash_response.status_code != 200:
                    print(f"      Bash move also failed: {bash_response.status_code}")
                    return False, 0
                
                # Check if bash move worked
                bash_result = bash_response.json()
                if 'commandResult' in bash_result and 'No such file' in bash_result['commandResult']:
                    print(f"      Source file not found: {bash_result['commandResult']}")
                    return False, 0
                
                print(f"      ✓ File moved using bash command")
            else:
                print(f"      ✓ File moved using unix-mv")
            
            # Now download via file transfer API
            download_url = f"{self.base_url}/mgmt/shared/file-transfer/downloads/{filename}"
            
            success, file_size = self._perform_download(download_url, filename)
            
            # If download failed, try to move the file back to original location
            if not success and actual_path:
                print(f"      Download failed, attempting to restore file...")
                restore_payload = {
                    "command": "run",
                    "utilCmdArgs": f"/var/config/rest/downloads/{filename} {source_path}"
                }
                self.session.post(move_url, json=restore_payload, timeout=30)
            else:
                # Clean up the file from downloads directory if still there
                cleanup_payload = {
                    "command": "run",
                    "utilCmdArgs": f"-c 'rm -f /var/config/rest/downloads/{filename}'"
                }
                self.session.post(f"{self.base_url}/mgmt/tm/util/bash", json=cleanup_payload, timeout=30)
            
            return success, file_size
            
        except Exception as e:
            print(f"      File transfer method failed: {str(e)}")
            return False, 0
    
    def _download_via_bash_copy(self, qkview_info, filename, actual_path=None):
        """Download using bash to copy file to download location"""
        try:
            source_path = actual_path or f"/var/tmp/{filename}"
            print(f"      Using bash to copy QKView from {source_path}...")
            
            # Use bash to copy file to the file transfer download directory
            bash_url = f"{self.base_url}/mgmt/tm/util/bash"
            
            # First, verify the source file exists and get its size
            verify_payload = {
                "command": "run", 
                "utilCmdArgs": f"-c 'ls -la \"{source_path}\"'"
            }
            
            verify_response = self.session.post(bash_url, json=verify_payload, timeout=30)
            if verify_response.status_code == 200:
                verify_result = verify_response.json()
                if 'commandResult' in verify_result:
                    command_result = verify_result['commandResult']
                    if 'No such file' not in command_result:
                        print(f"      Source file verified: {command_result.strip()}")
                        # Try to extract file size from ls output
                        try:
                            import re
                            size_match = re.search(r'\s+(\d+)\s+', command_result)
                            if size_match:
                                file_size = int(size_match.group(1))
                                print(f"      Expected file size: {file_size / (1024*1024):.1f} MB")
                        except:
                            pass
                    else:
                        print(f"      Source file not found: {command_result}")
                        return False, 0
            
            # Copy file to download directory
            copy_payload = {
                "command": "run", 
                "utilCmdArgs": f"-c 'cp \"{source_path}\" \"/var/config/rest/downloads/{filename}\"'"
            }
            
            response = self.session.post(bash_url, json=copy_payload, timeout=120)
            if response.status_code != 200:
                print(f"      Bash copy failed: {response.status_code}")
                return False, 0
            
            # Check if copy was successful
            result = response.json()
            if 'commandResult' in result and 'No such file' in result['commandResult']:
                print(f"      Source file not found during copy: {result['commandResult']}")
                return False, 0
            
            print(f"      ✓ File copied to download directory")
            
            # Download from the file transfer API
            download_url = f"{self.base_url}/mgmt/shared/file-transfer/downloads/{filename}"
            
            success, file_size = self._perform_download(download_url, filename)
            
            # Clean up the copied file regardless of success
            cleanup_payload = {
                "command": "run",
                "utilCmdArgs": f"-c 'rm -f /var/config/rest/downloads/{filename}'"
            }
            self.session.post(bash_url, json=cleanup_payload, timeout=30)
            
            return success, file_size
            
        except Exception as e:
            print(f"      Bash copy method failed: {str(e)}")
            return False, 0
    
    def _perform_download(self, download_url, filename):
        """Perform the actual file download"""
        try:
            local_dir = "QKViews"
            local_path = os.path.join(local_dir, filename)
            
            # Create download session with same authentication
            download_session = requests.Session()
            download_session.verify = False
            
            if self.token:
                download_session.headers.update({
                    'X-F5-Auth-Token': self.token
                })
            
            print(f"      Starting download from: {download_url}")
            
            # Download the file with progress indication
            response = download_session.get(
                download_url,
                timeout=self.qkview_timeout,
                stream=True
            )
            response.raise_for_status()
            
            # Get file size from headers if available
            total_size = int(response.headers.get('content-length', 0))
            if total_size > 0:
                print(f"      QKView file size: {total_size / (1024*1024):.1f} MB")
            else:
                print(f"      QKView file size: Unknown (no Content-Length header)")
            
            # Save file locally with progress
            downloaded = 0
            chunk_size = 64 * 1024  # 64KB chunks
            last_progress = 0
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Progress update every 10% or 10MB, whichever is smaller
                        if total_size > 0:
                            progress = (downloaded / total_size) * 100
                            progress_threshold = min(10, (10 * 1024 * 1024 / total_size) * 100)
                            if progress >= last_progress + progress_threshold:
                                print(f"        Download progress: {progress:.1f}% ({downloaded / (1024*1024):.1f} MB)")
                                last_progress = progress
                        else:
                            # Show progress every 10MB when size is unknown
                            if downloaded % (10 * 1024 * 1024) == 0:
                                print(f"        Downloaded: {downloaded / (1024*1024):.1f} MB")
            
            final_size = os.path.getsize(local_path)
            print(f"      ✓ Downloaded: {filename} ({final_size / (1024*1024):.1f} MB)")
            
            # Check if we got a reasonable file size (should be > 5MB for most QKViews)
            if final_size < 5 * 1024 * 1024:  # Less than 5MB
                print(f"      ⚠ Warning: Downloaded file seems small for a QKView ({final_size / (1024*1024):.1f} MB)")
                print(f"      This might be a partial download or error response")
                
                # Try to read first few bytes to see if it's an error response
                try:
                    with open(local_path, 'rb') as f:
                        first_bytes = f.read(100)
                        if b'<html>' in first_bytes.lower() or b'error' in first_bytes.lower():
                            print(f"      ✗ File appears to be an error response, not a QKView")
                            return False, final_size
                except:
                    pass
            
            # Verify file size if we know the expected size
            if total_size > 0:
                if abs(final_size - total_size) > 1024:  # Allow 1KB difference
                    print(f"      Warning: File size mismatch. Expected: {total_size / (1024*1024):.1f} MB, Downloaded: {final_size / (1024*1024):.1f} MB")
                    return False, final_size
                else:
                    print(f"      ✓ File size verified: {final_size / (1024*1024):.1f} MB")
            
            return True, final_size
            
        except requests.exceptions.Timeout:
            print(f"      Download timed out")
            return False, 0
        except Exception as e:
            print(f"      Download failed: {str(e)}")
            return False, 0
    
    def _cleanup_qkview_task(self, task_id):
        """Clean up QKView task using F5 autodeploy endpoint"""
        try:
            cleanup_url = f"{self.base_url}/mgmt/cm/autodeploy/qkview/{task_id}"
            
            print(f"    Cleaning up QKView task: {task_id}")
            response = self.session.delete(cleanup_url, timeout=30)
            response.raise_for_status()
            
            print(f"    ✓ QKView task cleaned up successfully")
            
        except Exception as e:
            print(f"    Warning: Failed to cleanup QKView task {task_id}: {str(e)}")
    
    def _cleanup_qkview_file(self, filename):
        """Clean up QKView file from /var/tmp after download"""
        try:
            cleanup_url = f"{self.base_url}/mgmt/tm/util/unix-rm"
            cleanup_payload = {
                "command": "run",
                "utilCmdArgs": f"/var/tmp/{filename}"
            }
            
            print(f"    Cleaning up original QKView file...")
            response = self.session.post(cleanup_url, json=cleanup_payload, timeout=30)
            response.raise_for_status()
            
            print(f"    ✓ Original QKView file cleaned up")
            
        except Exception as e:
            print(f"    Warning: Failed to cleanup original QKView file: {str(e)}")
    
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
            
            return None
            
        except Exception as e:
            print(f"    Error extracting platform: {str(e)}")
            return None
    
    def get_device_serial(self):
        """Extract device serial number"""
        try:
            print("  Searching for chassis serial number...")
            
            # Check sys/hardware directly for bigipChassisSerialNum
            print("  Checking sys/hardware for bigipChassisSerialNum...")
            hardware_data = self.api_request("sys/hardware")
            
            if hardware_data:
                # Extract it properly from the structure
                serial = self._extract_chassis_serial_from_hardware(hardware_data)
                if serial:
                    self.device_info['serial_number'] = serial
                    print(f"  SUCCESS: Found chassis serial: {serial}")
                    return
                
                # Also try to extract bigipChassisSerialNum recursively
                serial = self._find_bigip_chassis_serial(hardware_data)
                if serial:
                    self.device_info['serial_number'] = serial
                    print(f"  SUCCESS: Found bigipChassisSerialNum: {serial}")
                    return
            
            print("  Chassis serial number not found")
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
    
    def get_registration_key(self):
        """Extract registration key information"""
        try:
            print("  Searching for registration key...")
            
            # Check sys/license for registrationKey
            print("  Checking sys/license for registration key...")
            license_data = self.api_request("sys/license")
            
            if license_data:
                print(f"    Searching license data for registration key...")
                
                # Look for the registration key in the structured data
                reg_key = self._extract_registration_key_from_license(license_data)
                if reg_key:
                    self.device_info['registration_key'] = reg_key
                    print(f"  SUCCESS: Found registration key: {reg_key}")
                    return
            
            print("  Registration key not found")
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
            
            return None
            
        except Exception as e:
            print(f"    Error extracting registration key: {str(e)}")
            return None
    
    def get_software_version(self):
        """Extract software version information"""
        try:
            active_version = 'N/A'
            available_versions = []
            
            # Try sys/software/volume for boot locations
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
            
            # Fallback: Try sys/version for TMOS version if no active version
            if active_version == 'N/A':
                print("  Trying sys/version for TMOS info...")
                tmos_data = self.api_request("sys/version")
                if tmos_data and 'entries' in tmos_data:
                    for entry_name, entry_data in tmos_data['entries'].items():
                        nested_stats = entry_data.get('nestedStats', {})
                        entries = nested_stats.get('entries', {})
                        
                        if 'Version' in entries:
                            version_info = entries['Version'].get('description', '')
                            if version_info and version_info != 'N/A':
                                active_version = version_info
                                print(f"  Found version: {active_version}")
                                break
            
            # Check for additional software information
            print("  Checking for additional software information...")
            
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
            # System clock/time - improved
            print("  Getting system time...")
            self._get_system_time_improved()
            
            # Memory information - improved
            print("  Getting memory information...")
            self._get_memory_info_improved()
            
            # CPU information
            print("  Getting CPU information...")
            cpu_data = self.api_request("sys/cpu")
            if cpu_data and 'entries' in cpu_data:
                cpu_count = len(cpu_data['entries'])
                self.device_info['cpu_count'] = cpu_count
                print(f"    Found {cpu_count} CPU entries")
            else:
                self.device_info['cpu_count'] = 'N/A'
                print("    CPU data not available")
            
            # HA status - improved
            print("  Getting HA status...")
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
                        print(f"    Found system time: {formatted_time}")
                        return
        
        # Method 2: Try getting from sys/global-settings
        try:
            global_data = self.api_request("sys/global-settings")
            if global_data and 'consoleInactivityTimeout' in global_data:
                # Device is responding, use current timestamp as fallback
                from datetime import datetime
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self.device_info['system_time'] = current_time
                print(f"    Using local timestamp: {current_time}")
                return
        except:
            pass
        
        print("    Could not determine system time")
    
    def _get_memory_info_improved(self):
        """Improved memory information extraction with better fallbacks"""
        # Initialize memory fields
        self.device_info.update({
            'total_memory': 'N/A',
            'memory_used': 'N/A', 
            'tmm_memory': 'N/A'
        })
        
        # Method 1: Try sys/tmm-info for TMM memory (this works!)
        print("    Trying sys/tmm-info for TMM memory...")
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
                                print(f"    Found TMM memory: {formatted_mem}")
                                break
        
        # Method 2: Try sys/host-info for host memory
        print("    Trying sys/host-info for host memory...")
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
                                    print(f"    Found total memory: {formatted_mem}")
                                elif 'used' in field_name.lower() and self.device_info['memory_used'] == 'N/A':
                                    self.device_info['memory_used'] = formatted_mem
                                    print(f"    Found used memory: {formatted_mem}")
        
        # Method 3: Try sys/platform for memory info
        if self.device_info['total_memory'] == 'N/A':
            print("    Trying sys/platform for memory...")
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
                                        print(f"    Found memory in platform: {formatted_mem}")
                                        break
        
        print(f"    Memory Results: Total={self.device_info['total_memory']}, Used={self.device_info['memory_used']}, TMM={self.device_info['tmm_memory']}")
    
    def _get_ha_status_improved(self):
        """Improved HA status detection with multiple methods"""
        self.device_info['ha_status'] = 'N/A'
        
        # Method 1: Try sys/failover
        try:
            failover_data = self.api_request("sys/failover")
            if failover_data:
                if 'status' in failover_data:
                    self.device_info['ha_status'] = failover_data['status']
                    print(f"    Found HA status: {failover_data['status']}")
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
                                    print(f"    Found HA status in entries: {status_value}")
                                    return
        except:
            pass
        
        # Method 2: Try cm/device to check for clustering
        try:
            device_data = self.api_request("cm/device")
            if device_data and 'items' in device_data:
                device_count = len(device_data['items'])
                if device_count > 1:
                    self.device_info['ha_status'] = f'Clustered ({device_count} devices)'
                    print(f"    Found clustering: {device_count} devices")
                    return
                else:
                    self.device_info['ha_status'] = 'Standalone'
                    print(f"    Single device detected: Standalone")
                    return
        except:
            pass
        
        # Method 3: Default to Standalone
        self.device_info['ha_status'] = 'Standalone'
        print(f"    Using default: Standalone")
    
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
            print(f"      Error formatting memory value '{memory_value}': {str(e)}")
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
                        print(f"    Converted UTC time: {time_string} -> {formatted_time} (local)")
                    else:
                        # Assume it's already in local time
                        formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                        print(f"    Converted local time: {time_string} -> {formatted_time}")
                    
                    return formatted_time
                except ValueError:
                    continue
            
            # If all else fails, return the original string
            return time_string
            
        except Exception as e:
            print(f"    Error formatting time '{time_string}': {str(e)}")
            return time_string
    
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
        
        # Create and download QKView if requested
        if self.create_qkview:
            print("Creating and downloading QKView...")
            qkview_success = self.create_and_download_qkview()
            self.device_info['qkview_downloaded'] = 'Yes' if qkview_success else 'Failed'
        else:
            self.device_info['qkview_downloaded'] = 'Not requested'
        
        # Add extraction timestamp
        self.device_info['extraction_timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Clean up session
        self.logout()
        
        return True

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

def get_credentials_for_device(args, device_user=None, device_pass=None):
    """Get credentials for a specific device with fallback logic"""
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
    if args.qkview:
        print("QKView creation and download enabled using F5 autodeploy endpoint")
        print(f"QKView timeout: {args.qkview_timeout} seconds ({args.qkview_timeout/60:.1f} minutes)")
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
        extractor = BigIPInfoExtractor(
            device['ip'], 
            username, 
            password, 
            create_qkview=args.qkview,
            qkview_timeout=args.qkview_timeout
        )
        
        if extractor.extract_all_info():
            devices_info.append(extractor.device_info)
            print(f"  ✓ Successfully extracted information from {device['ip']}")
            
            # Display brief summary
            hostname = extractor.device_info.get('hostname', 'N/A')
            version = extractor.device_info.get('active_version', 'N/A')
            qkview_status = extractor.device_info.get('qkview_downloaded', 'N/A')
            print(f"    Hostname: {hostname}, Version: {version}")
            if args.qkview:
                print(f"    QKView: {qkview_status}")
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
                    extractor = BigIPInfoExtractor(
                        device['ip'], 
                        retry_username, 
                        retry_password,
                        create_qkview=args.qkview,
                        qkview_timeout=args.qkview_timeout
                    )
                    if extractor.extract_all_info():
                        devices_info.append(extractor.device_info)
                        print(f"  ✓ Successfully extracted information from {device['ip']} (retry)")
                        hostname = extractor.device_info.get('hostname', 'N/A')
                        version = extractor.device_info.get('active_version', 'N/A')
                        qkview_status = extractor.device_info.get('qkview_downloaded', 'N/A')
                        print(f"    Hostname: {hostname}, Version: {version}")
                        if args.qkview:
                            print(f"    QKView: {qkview_status}")
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
        extractor = BigIPInfoExtractor(
            host, 
            username, 
            password, 
            create_qkview=args.qkview,
            qkview_timeout=args.qkview_timeout
        )
        
        if extractor.extract_all_info():
            devices_info.append(extractor.device_info)
            print(f"Successfully extracted information from {host}")
            
            # Display summary
            print("\nDevice Summary:")
            print(f"  Hostname: {extractor.device_info.get('hostname', 'N/A')}")
            print(f"  Serial: {extractor.device_info.get('serial_number', 'N/A')}")
            print(f"  Version: {extractor.device_info.get('active_version', 'N/A')}")
            print(f"  Emergency Hotfixes: {extractor.device_info.get('emergency_hotfixes', 'None')}")
            if args.qkview:
                print(f"  QKView: {extractor.device_info.get('qkview_downloaded', 'N/A')}")
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
                    extractor = BigIPInfoExtractor(
                        host, 
                        username, 
                        password,
                        create_qkview=args.qkview,
                        qkview_timeout=args.qkview_timeout
                    )
                    if extractor.extract_all_info():
                        devices_info.append(extractor.device_info)
                        print(f"Successfully extracted information from {host}")
                        
                        # Display summary
                        print("\nDevice Summary:")
                        print(f"  Hostname: {extractor.device_info.get('hostname', 'N/A')}")
                        print(f"  Serial: {extractor.device_info.get('serial_number', 'N/A')}")
                        print(f"  Version: {extractor.device_info.get('active_version', 'N/A')}")
                        print(f"  Emergency Hotfixes: {extractor.device_info.get('emergency_hotfixes', 'None')}")
                        if args.qkview:
                            print(f"  QKView: {extractor.device_info.get('qkview_downloaded', 'N/A')}")
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
    python %(prog)s --in devices.csv --qkview --out results.csv  # Include QKView creation
    python %(prog)s -q --qkview-timeout 1200 --in devices.csv    # QKView with 20min timeout
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
    parser.add_argument('--qkview', '-q',
                       action='store_true',
                       help='Create and download QKView from each device using F5 autodeploy endpoint')
    parser.add_argument('--qkview-timeout',
                       type=int,
                       default=1200,
                       help='Timeout for QKView creation in seconds (default: 1200)')
    parser.add_argument('--no-qkview',
                       action='store_true',
                       help='Disable QKView creation (default behavior)')
    
    args = parser.parse_args()
    
    # Handle QKView options
    if args.no_qkview:
        args.qkview = False
    
    # Security warning for password in command line
    if args.password:
        print("WARNING: Using password in command line arguments is not secure.")
        print("Consider using --user only and entering password interactively.\n")
    
    # QKView information
    if args.qkview:
        print("QKView creation enabled using F5 autodeploy endpoint")
        print(f"QKView timeout set to {args.qkview_timeout} seconds ({args.qkview_timeout/60:.1f} minutes)")
        print("QKViews will be downloaded to the 'QKViews' directory")
        print("This will take additional time per device\n")
        
        # Create local QKViews directory if it doesn't exist
        qkviews_dir = "QKViews"
        if not os.path.exists(qkviews_dir):
            os.makedirs(qkviews_dir)
            print(f"Created local directory: {qkviews_dir}")
        else:
            print(f"Using existing directory: {qkviews_dir}")
        print("")
    
    print("BIG-IP Device Information Extractor")
    print("=" * 40)
    
    # Determine processing mode
    if args.input_file:
        # Process devices from CSV file
        devices_info = process_devices_from_file(args)
    else:
        # Interactive mode
        devices_info = process_devices_interactively(args)
    
    # Write results to CSV
    if devices_info:
        write_to_csv(devices_info, args.out)
        print(f"\nExtracted information for {len(devices_info)} device(s)")
        print(f"Results written to: {args.out}")
        if args.qkview:
            qkview_count = sum(1 for device in devices_info if device.get('qkview_downloaded') == 'Yes')
            print(f"QKViews downloaded: {qkview_count}/{len(devices_info)}")
            if qkview_count > 0:
                print(f"QKView files saved in: ./QKViews/")
    else:
        print("No device information collected.")
        # Still create an empty CSV file with headers
        write_to_csv([], args.out)
        print(f"Empty CSV file created: {args.out}")

if __name__ == "__main__":
    main()

