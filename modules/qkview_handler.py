"""
QKView Handler Module

Handles QKView creation and download using F5's official autodeploy endpoint
with proper asynchronous task monitoring and enhanced error handling.
"""

import json
import os
import time
import re
import traceback
from datetime import datetime
import requests

from .colors import Colors


class QKViewHandler:
    def __init__(self, session, base_url, qkview_timeout=1200, no_delete=False, verbose=False):
        """Initialize QKView handler"""
        self.session = session
        self.base_url = base_url
        self.qkview_timeout = qkview_timeout
        self.no_delete = no_delete
        self.verbose = verbose
        self.token = None
        self.device_info = {}
    
    def set_token(self, token):
        """Set authentication token"""
        self.token = token
    
    def set_device_info(self, device_info):
        """Set device information"""
        self.device_info = device_info
    
    def create_and_download_qkview(self):
        """Create QKView on remote device and download it using enhanced F5 autodeploy endpoint"""
        try:
            if not self.verbose:
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
                print(f"  {Colors.green('✓')} QKView downloaded successfully")
                
                # Step 4: Cleanup logic based on --no-delete flag
                filename = qkview_info.get('name')
                if filename and downloaded_file_size > 5 * 1024 * 1024:  # Only cleanup if > 5MB
                    if self.no_delete:
                        print(f"  {Colors.yellow('ℹ')} Cleanup disabled by --no-delete option")
                        print(f"  Remote QKView file: /var/tmp/{filename}")
                    else:
                        print(f"  Cleaning up remote files...")
                        self._cleanup_qkview_file(filename)
                        self._cleanup_qkview_task(task_id)
                        print(f"  {Colors.green('✓')} Remote cleanup completed")
                elif filename:
                    if downloaded_file_size <= 5 * 1024 * 1024:
                        print(f"  {Colors.yellow('⚠')} Small file size ({downloaded_file_size / (1024*1024):.1f} MB) - skipping cleanup for safety")
                    if self.no_delete:
                        print(f"  {Colors.yellow('ℹ')} Cleanup disabled by --no-delete option")
                    print(f"  Remote QKView file: /var/tmp/{filename}")
                
                return True
            else:
                print("  ✗ Failed to download QKView")
                # Don't cleanup if download failed - leave files for debugging
                filename = qkview_info.get('name', 'unknown')
                print(f"  {Colors.yellow('ℹ')} Remote files left for debugging since download failed")
                print(f"  Remote QKView file: /var/tmp/{filename}")
                return False
                
        except Exception as e:
            print(f"  ✗ Error creating/downloading QKView: {str(e)}")
            print(f"  Traceback: {traceback.format_exc()}")
            return False
    
    def _create_qkview_task(self):
        """Create QKView task using F5 autodeploy endpoint"""
        try:
            # Generate a unique QKView name with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            hostname = self.device_info.get('hostname', self.base_url.split('//')[1])
            
            # Clean hostname for filename (remove special characters)
            clean_hostname = re.sub(r'[^\w\-_\.]', '_', hostname)
            
            # IMPORTANT: Only provide the filename, not a path!
            # F5 will automatically place it in /var/tmp/
            qkview_name = f"{clean_hostname}_{timestamp}.qkview"
            
            # Use the F5 autodeploy endpoint
            qkview_url = f"{self.base_url}/mgmt/cm/autodeploy/qkview"
            
            # Payload according to F5 documentation - just the filename
            qkview_payload = {"name": qkview_name}
            
            print(f"    Creating QKView task: {qkview_name}")
            print(f"    The BIG-IP will save to: /var/tmp/{qkview_name} on the BIG-IP")
            if self.verbose:
                print(f"    Payload being sent: {json.dumps(qkview_payload)}")
            
            # Submit QKView creation request (asynchronous)
            try:
                if self.verbose:
                    print(f"    Sending POST to: {qkview_url}")
                response = self.session.post(
                    qkview_url,
                    json=qkview_payload,
                    timeout=30  # Quick timeout for task creation
                )
                if self.verbose:
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
                    if self.verbose:
                        print(f"    Raw response: {json.dumps(response_data, indent=2)}")
                except:
                    response_data = {}
                
                # Extract the task ID from the response
                task_id = response_data.get('id')
                if task_id:
                    print(f"    {Colors.green('✓')} QKView task created with ID: {Colors.light_blue(task_id)}")
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
            print(f"      Status check for task {Colors.magenta(task_id)}")
            
            status_url = f"{self.base_url}/mgmt/cm/autodeploy/qkview/{task_id}"
            start_time = time.time()
            check_interval = 15  # Check every 15 seconds
            check_count = 0
            spinner_chars = ['/', '-', '\\', '|']
            spinner_index = 0
            current_status = 'Unknown'
            current_generation = 'N/A'
            last_printed_line = ""  # Track what we last printed to avoid duplicates
            
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
                        print(f'\x1b[2K\r      {Colors.green("✓")} [{elapsed}s] Task Status (Generation: {current_generation}): the task completed successfully!')
                        print(f'    {Colors.green("✓")} QKView generation completed successfully (after {elapsed}s)')
                        return result
                    
                    elif current_status == 'FAILED':
                        print(f'\x1b[2K\r      [{elapsed}s] Task Status (Generation: {current_generation}): {current_status} : Failed!')
                        print(f'    ✗ QKView generation failed (after {elapsed}s)')
                        return None
                    
                    elif current_status == 'IN_PROGRESS':
                        # Show spinning progress indicator with countdown - exactly like original
                        for i in range(check_interval):
                            spinner = spinner_chars[spinner_index % len(spinner_chars)]
                            remaining = check_interval - i
                            elapsed_current = elapsed + i
                            
                            # Use the exact same format and method as the original script
                            print(f'\x1b[2K\r      [{elapsed_current}s] Task Status (Generation: {current_generation}): {current_status} : Waiting {remaining} seconds before next check... {spinner}', end='', flush=True)
                            
                            spinner_index += 1
                            time.sleep(1)
                    else:
                        status_line = f'      [{elapsed}s] Task Status (Generation: {current_generation}): {current_status} : Unknown status'
                        if status_line != last_printed_line:
                            print(f'\x1b[2K\r{status_line}', end='', flush=True)
                            last_printed_line = status_line
                        time.sleep(check_interval)
                
                except requests.exceptions.RequestException as e:
                    error_line = f'      [{elapsed}s] Task Status (Generation: {current_generation}): ERROR : Connection failed (attempt {check_count})'
                    if error_line != last_printed_line:
                        print(f'\x1b[2K\r{error_line}', end='', flush=True)
                        last_printed_line = error_line
                    if check_count >= 3:
                        print(f'\n    ✗ Multiple consecutive failures, aborting')
                        return None
                    time.sleep(check_interval)
            
            elapsed = int(time.time() - start_time)
            print(f'\x1b[2K\r      [{elapsed}s] Task Status (Generation: {current_generation}): TIMEOUT : Exceeded {self.qkview_timeout}s limit')
            print(f'    ✗ QKView creation timed out after {elapsed} seconds')
            return None
            
        except Exception as e:
            elapsed = int(time.time() - start_time) if 'start_time' in locals() else 0
            print(f'\x1b[2K\r      [{elapsed}s] Task Status (Generation: N/A): ERROR : {str(e)}')
            print(f'    ✗ Error waiting for QKView completion')
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
                            print(f"    {Colors.green('✓')} Download successful.")
                            return True, file_size
                        else:
                            print(f"    ✗ Download failed using {method_name}")
                    elif result:
                        # Legacy method that returns boolean only
                        print(f"    {Colors.green('✓')} Download successful.")
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
                            if self.verbose:
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
            
            if self.verbose:
                print(f"      Using F5 official chunked download method")
                print(f"      Autodeploy URI: {qkview_uri}")
            
            # Handle localhost replacement in URI
            if 'localhost' in qkview_uri:
                download_url = qkview_uri.replace('localhost', self.base_url.split('//')[1])
            elif qkview_uri.startswith('https://'):
                download_url = qkview_uri
            else:
                download_url = f"https://{self.base_url.split('//')[1]}{qkview_uri}"
            
            if self.verbose:
                print(f"      Download URL: {download_url}")
            
            return self._download_chunked_f5_method(download_url, filename)
            
        except Exception as e:
            print(f"      Autodeploy URI method failed: {str(e)}")
            return False, 0
    
    def _download_chunked_f5_method(self, download_url, filename):
        """Download using F5's official chunked method - corrected version based on K04396542"""
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
                        # Get the Content-Range header to determine total file size
                        crange = resp.headers.get('Content-Range', '')
                        
                        # Determine the total number of bytes to read (F5 method)
                        if size == 0:
                            try:
                                # F5 does: size = int(crange.split('/')[-1]) - 1
                                # This makes size 0-based (last byte position)
                                size = int(crange.split('/')[-1]) - 1
                                total_chunks = ((size + 1) // chunk_size) + (1 if (size + 1) % chunk_size else 0)
                                if self.verbose:
                                    print(f"        Total file size determined: {size + 1} bytes ({size + 1 / (1024*1024):.1f} MB, {total_chunks} chunks)")
                                
                                # If the file is smaller than the chunk size, adjust end
                                if chunk_size > size:
                                    end = size
                                    
                            except (ValueError, IndexError) as e:
                                print(f"\r        Could not determine file size from Content-Range: {crange}, error: {e}")
                                return False, 0
                        
                        # If the size is zero (first iteration), don't write data yet
                        # This matches F5's logic exactly
                        if size > 0:
                            current_bytes += chunk_size
                            bytes_written_this_chunk = 0
                            for chunk in resp.iter_content(chunk_size=8192):
                                if chunk:  # Filter out keep-alive chunks
                                    f.write(chunk)
                                    bytes_written_this_chunk += len(chunk)
                            
                            # Calculate and show progress
                            actual_current_bytes = f.tell()
                            progress = (actual_current_bytes / (size + 1)) * 100
                            chunk_display = f"(Chunk {chunk_count}/{total_chunks})" if total_chunks > 0 else f"(Chunk {chunk_count})"
                            print(f"\r        Progress: {progress:.1f}% ({actual_current_bytes / (1024*1024):.1f} MB / {(size + 1) / (1024*1024):.1f} MB) {chunk_display}", end='', flush=True)
                        
                        # Once we've downloaded the entire file, break out of the loop
                        # F5 uses: if end == size:
                        if end == size:
                            print(f"\n        {Colors.green('✓')} Download complete!")
                            break
                        
                        # Calculate next chunk range (F5 method)
                        start += chunk_size
                        if (current_bytes + chunk_size) > (size + 1):
                            end = size
                        else:
                            end = start + chunk_size - 1
                            
                    elif resp.status_code == 206:  # Partial Content
                        print(f"        Unexpected 206 response on what should be 200")
                        # Handle similar to 200 but this might indicate an issue
                        continue
                        
                    elif resp.status_code == 400:
                        print(f"\r        HTTP 400 - checking if this is expected end-of-file                              ")
                        
                        # Check if we're at or very near the end
                        current_file_size = f.tell()
                        if current_file_size > 0 and size > 0:
                            expected_size = size + 1
                            if abs(current_file_size - expected_size) <= 1024:  # Within 1KB
                                print(f"\n        Download appears complete despite HTTP 400")
                                print(f"        Expected: {expected_size}, Got: {current_file_size}")
                                break
                        
                        print(f"\r        Unexpected HTTP 400 at chunk {chunk_count}                              ")
                        print(f"\r        Current file size: {f.tell() if hasattr(f, 'tell') else 'unknown'}                              ")
                        print(f"\r        Expected total: {size + 1 if size > 0 else 'unknown'}                              ")
                        return False, 0
                        
                    else:
                        print(f"\r        Unexpected response code: {resp.status_code}                              ")
                        print(f"\r        Response text: {resp.text[:200]}                              ")
                        return False, 0
            
            final_size = os.path.getsize(local_path)
            print(f"\n      {Colors.green('✓')} F5 chunked download completed: {filename}")
            print(f"      Final file size: {final_size} bytes ({final_size / (1024*1024):.1f} MB)")
            
            # Verify file size matches expected
            if size > 0:
                expected_size = size + 1  # Convert from 0-based to actual byte count
                size_difference = abs(final_size - expected_size)
                
                print(f"      Expected size: {expected_size} bytes")
                print(f"      Actual size: {final_size} bytes") 
                if size_difference == 0:
                    print(f"      {Colors.green('✓')} Difference: {size_difference} bytes")
                    print(f"      {Colors.green('✓')} File size matches exactly!")
                elif size_difference <= 1024:  # 1KB tolerance
                    print(f"      {Colors.red('✗')} Difference: {size_difference} bytes")
                    print(f"      {Colors.green('✓')} File size within acceptable tolerance")
                else:
                    print(f"      {Colors.red('✗')} Difference: {size_difference} bytes")
                    print(f"      {Colors.yellow('⚠')} Warning: Significant file size difference")
                    print(f"      This may indicate a download problem")
                    
                    # Don't fail if we got most of the file
                    if final_size >= expected_size * 0.95:  # At least 95%
                        print(f"      {Colors.green('✓')} File size is acceptable (95%+ of expected)")
                    else:
                        return False, final_size
            
            # Basic sanity check
            if final_size < 1024 * 1024:  # Less than 1MB is suspicious
                print(f"      {Colors.yellow('⚠')} Warning: File seems very small for a QKView")
                
                # Check if it's an error response
                try:
                    with open(local_path, 'rb') as f:
                        first_bytes = f.read(100)
                        if b'<html>' in first_bytes.lower() or b'error' in first_bytes.lower():
                            print(f"      ✗ File appears to be an error response")
                            return False, final_size
                except:
                    pass
            
            return True, final_size
            
        except Exception as e:
            print(f"\n      F5 chunked download failed with exception: {str(e)}")
            print(f"      Traceback: {traceback.format_exc()}")
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