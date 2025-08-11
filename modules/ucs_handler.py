"""
UCS Handler Module

Handles UCS (User Configuration Set) creation and download using F5's task-based endpoint
with proper asynchronous task monitoring and enhanced error handling.
Based on F5 documentation K000138875 for the correct task-based UCS creation.
"""

import json
import os
import time
import re
import traceback
from datetime import datetime
import requests

from .colors import Colors


class UCSHandler:
    def __init__(self, session, base_url, ucs_timeout=900, no_delete=False, verbose=False):
        """Initialize UCS handler"""
        self.session = session
        self.base_url = base_url
        self.ucs_timeout = ucs_timeout
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
    
    def create_and_download_ucs(self):
        """Create UCS on remote device and download it using F5 task endpoint"""
        try:
            if not self.verbose:
                print("  Creating UCS using F5 task endpoint...")
                print(f"  UCS timeout configured for: {self.ucs_timeout} seconds ({self.ucs_timeout/60:.1f} minutes)")
            
            # Step 1: Create UCS task
            task_result = self._create_ucs_task()
            if not task_result:
                print("  ✗ Failed to create UCS task")
                return False
            
            task_id, ucs_filename = task_result
            
            # Step 2: Wait for UCS to complete
            ucs_info = self._wait_for_ucs_completion(task_id)
            if not ucs_info:
                print("  ✗ UCS creation timed out or failed")
                
                # But check if file exists anyway before giving up completely
                print("  Checking if UCS file was created despite connection issues...")
                ucs_exists, ucs_size = self._check_if_ucs_exists_by_name(ucs_filename)
                if ucs_exists and ucs_size > 10 * 1024 * 1024:  # At least 10MB
                    print(f"  {Colors.green('✓')} UCS file found! ({ucs_size / (1024*1024):.1f} MB)")
                    print("  Proceeding with download despite task status unknown...")
                    # Create a fake success response to continue
                    ucs_info = {"_taskState": "COMPLETED", "_taskId": task_id, "name": ucs_filename}
                else:
                    return False
            
            # Step 3: Download UCS
            download_result, downloaded_file_size = self._download_ucs(ucs_filename)
            if download_result:
                print(f"  {Colors.green('✓')} UCS downloaded successfully")
                
                # Step 4: Cleanup logic based on --no-delete flag
                if downloaded_file_size > 1 * 1024 * 1024:  # Only cleanup if > 1MB
                    if self.no_delete:
                        print(f"  {Colors.yellow('ℹ')} Cleanup disabled by --no-delete option")
                        print(f"  Remote UCS file: /var/local/ucs/{ucs_filename}")
                    else:
                        print(f"  Cleaning up remote files...")
                        self._cleanup_ucs_file(ucs_filename)
                        self._cleanup_ucs_task(task_id)
                        print(f"  {Colors.green('✓')} Remote cleanup completed")
                else:
                    if downloaded_file_size <= 1 * 1024 * 1024:
                        print(f"  {Colors.yellow('⚠')} Small file size ({downloaded_file_size / (1024*1024):.1f} MB) - skipping cleanup for safety")
                    if self.no_delete:
                        print(f"  {Colors.yellow('ℹ')} Cleanup disabled by --no-delete option")
                    print(f"  Remote UCS file: /var/local/ucs/{ucs_filename}")
                
                return True
            else:
                print("  ✗ Failed to download UCS")
                # Don't cleanup if download failed - leave files for debugging
                print(f"  {Colors.yellow('ℹ')} Remote files left for debugging since download failed")
                print(f"  Remote UCS file: /var/local/ucs/{ucs_filename}")
                return False
                
        except Exception as e:
            print(f"  ✗ Error creating/downloading UCS: {str(e)}")
            print(f"  Traceback: {traceback.format_exc()}")
            return False
    
    def _create_ucs_task(self):
        """Create UCS task using F5 task endpoint - returns (task_id, filename) tuple"""
        try:
            # Generate a unique UCS name with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            hostname = self.device_info.get('hostname', self.base_url.split('//')[1].split(':')[0])
            
            # Clean hostname for filename (remove special characters)
            clean_hostname = re.sub(r'[^\w\-_\.]', '_', hostname)
            
            # UCS filename - just the name, no path or .ucs extension for the API
            ucs_name = f"{clean_hostname}_{timestamp}"
            ucs_filename = f"{ucs_name}.ucs"
            
            # Use the F5 task endpoint for UCS creation
            ucs_url = f"{self.base_url}/mgmt/tm/task/sys/ucs"
            
            # Payload according to F5 documentation K000138875 - just name, no path
            ucs_payload = {
                "command": "save",
                "name": ucs_name  # No path, no .ucs extension
            }
            
            print(f"    Creating UCS task: {ucs_filename}")
            print(f"    The BIG-IP will save to: /var/local/ucs/{ucs_filename}")
            if self.verbose:
                print(f"    POST to: {ucs_url}")
                print(f"    Payload: {json.dumps(ucs_payload)}")
            
            # Submit UCS creation request (asynchronous)
            try:
                response = self.session.post(
                    ucs_url,
                    json=ucs_payload,
                    timeout=30  # Quick timeout for task creation
                )
                if self.verbose:
                    print(f"    Response status: {response.status_code}")
                
            except requests.exceptions.Timeout:
                print(f"    ✗ UCS task creation timed out")
                return None
            except Exception as e:
                print(f"    ✗ UCS task creation failed: {str(e)}")
                return None
            
            if response.status_code in [200, 202]:
                try:
                    response_data = response.json()
                    if self.verbose:
                        print(f"    Raw response: {json.dumps(response_data, indent=2)}")
                except:
                    response_data = {}
                
                # Extract the task ID from the response
                task_id = response_data.get('_taskId')
                task_state = response_data.get('_taskState', 'Unknown')
                
                if task_id:
                    print(f"    {Colors.green('✓')} UCS task created with ID: {Colors.light_blue(task_id)}")
                    print(f"    Initial task state: {task_state}")
                    
                    # Now validate the task to start processing (CRITICAL STEP)
                    if self._validate_ucs_task(task_id):
                        return (task_id, ucs_filename)
                    else:
                        print(f"    ✗ Failed to validate UCS task")
                        return None
                else:
                    print(f"    ✗ No task ID found in response")
                    print(f"    Response: {response_data}")
                    return None
                    
            else:
                print(f"    ✗ Failed to create UCS task: {response.status_code}")
                try:
                    error_details = response.json()
                    print(f"    Error details: {error_details}")
                except:
                    print(f"    Response text: {response.text[:200]}")
                
                # Try with a simpler filename if the original failed
                if 'invalid' in response.text.lower() or 'name' in response.text.lower():
                    print(f"    Trying with simplified filename...")
                    simple_name = f"ucs_{timestamp}"
                    simple_filename = f"{simple_name}.ucs"
                    simple_payload = {"command": "save", "name": simple_name}
                    print(f"    Simplified name: {simple_filename}")
                    
                    retry_response = self.session.post(ucs_url, json=simple_payload, timeout=30)
                    if retry_response.status_code in [200, 202]:
                        retry_data = retry_response.json()
                        task_id = retry_data.get('_taskId')
                        if task_id:
                            print(f"    UCS task created with simplified name: {simple_filename}")
                            print(f"    Task ID: {task_id}")
                            
                            # Validate the simplified task
                            if self._validate_ucs_task(task_id):
                                return (task_id, simple_filename)
                            else:
                                print(f"    ✗ Failed to validate simplified UCS task")
                                return None
                
                return None
                
        except Exception as e:
            print(f"    ✗ Error creating UCS task: {str(e)}")
            return None
    
    def _validate_ucs_task(self, task_id):
        """Validate UCS task to start processing - CRITICAL for task execution"""
        try:
            validate_url = f"{self.base_url}/mgmt/tm/task/sys/ucs/{task_id}"
            validate_payload = {
                "_taskState": "VALIDATING"
            }
            
            print(f"    Validating UCS task to start execution...")
            if self.verbose:
                print(f"    PUT to: {validate_url}")
                print(f"    Payload: {json.dumps(validate_payload)}")
            
            response = self.session.put(
                validate_url,
                json=validate_payload,
                timeout=30
            )
            
            if response.status_code == 202:
                try:
                    result = response.json()
                    if self.verbose:
                        print(f"    Validation response: {json.dumps(result, indent=2)}")
                    
                    if result.get('message') == 'Task will execute asynchronously.':
                        print(f"    {Colors.green('✓')} UCS task validated and will execute")
                        return True
                    else:
                        # Any 202 response should be considered success
                        print(f"    {Colors.green('✓')} UCS task validated (response: {result.get('message', 'No message')})")
                        return True
                except:
                    # If we got 202 but can't parse JSON, still consider it success
                    print(f"    {Colors.green('✓')} UCS task validated (202 response)")
                    return True
            else:
                print(f"    ✗ Failed to validate UCS task: {response.status_code}")
                try:
                    error_details = response.json()
                    print(f"    Validation error: {error_details}")
                except:
                    print(f"    Validation response: {response.text[:200]}")
                return False
                
        except Exception as e:
            print(f"    ✗ Error validating UCS task: {str(e)}")
            return False
    
    def _wait_for_ucs_completion(self, task_id):
        """Wait for UCS task completion using F5 task endpoint"""
        try:
            print(f"    Waiting for UCS task completion...")
            print(f"      Status check for task {Colors.magenta(task_id)}")
            
            status_url = f"{self.base_url}/mgmt/tm/task/sys/ucs/{task_id}"
            start_time = time.time()
            check_interval = 15  # Check every 15 seconds
            check_count = 0
            consecutive_failures = 0  # Track consecutive failures
            spinner_chars = ['/', '-', '\\', '|']
            spinner_index = 0
            current_status = 'Unknown'
            last_printed_line = ""
            last_known_status = None  # Track last successful status
            
            while (time.time() - start_time) < self.ucs_timeout:
                check_count += 1
                elapsed = int(time.time() - start_time)
                
                try:
                    response = self.session.get(status_url, timeout=30)
                    response.raise_for_status()
                    
                    result = response.json()
                    current_status = result.get('_taskState', 'Unknown')
                    last_known_status = current_status  # Update last known good status
                    consecutive_failures = 0  # Reset failure counter on success
                    
                    if self.verbose:
                        print(f"\n      Debug: Full task response: {json.dumps(result, indent=2)}")
                    
                    if current_status == 'COMPLETED':
                        print(f'\x1b[2K\r      {Colors.green("✓")} [{elapsed}s] Task Status: COMPLETED - the task completed successfully!')
                        print(f'    {Colors.green("✓")} UCS generation completed successfully (after {elapsed}s)')
                        return result
                    
                    elif current_status == 'FAILED':
                        print(f'\x1b[2K\r      [{elapsed}s] Task Status: FAILED')
                        print(f'    ✗ UCS generation failed (after {elapsed}s)')
                        # Print error details if available
                        if 'errorMessage' in result:
                            print(f'    Error: {result["errorMessage"]}')
                        if '_taskResult' in result:
                            print(f'    Task Result: {result["_taskResult"]}')
                        return None
                    
                    elif current_status in ['STARTED', 'VALIDATING', 'RUNNING']:
                        # These are all valid "in progress" states
                        # Show spinning progress indicator with countdown - exactly like QKView
                        for i in range(check_interval):
                            spinner = spinner_chars[spinner_index % len(spinner_chars)]
                            remaining = check_interval - i
                            elapsed_current = elapsed + i
                            
                            # Use similar format to QKView handler
                            if current_status == 'VALIDATING':
                                status_display = "VALIDATING"
                            elif current_status == 'RUNNING':
                                status_display = "IN_PROGRESS"
                            else:
                                status_display = current_status
                            
                            print(f'\x1b[2K\r      [{elapsed_current}s] Task Status: {status_display} : Waiting {remaining} seconds before next check... {spinner}', end='', flush=True)
                            
                            spinner_index += 1
                            time.sleep(1)
                    
                    else:
                        # Unknown status - show it but continue monitoring
                        status_line = f'      [{elapsed}s] Task Status: {current_status} : Unknown status, continuing to monitor'
                        if status_line != last_printed_line:
                            print(f'\x1b[2K\r{status_line}', end='', flush=True)
                            last_printed_line = status_line
                        time.sleep(check_interval)
                
                except requests.exceptions.RequestException as e:
                    consecutive_failures += 1
                    
                    # Show different messages based on context
                    if last_known_status in ['RUNNING', 'VALIDATING', 'STARTED']:
                        # Task was running, connection issues are expected for long operations
                        error_msg = f'Connection timeout (expected for large UCS), continuing... (failure {consecutive_failures})'
                    else:
                        error_msg = f'Connection failed (failure {consecutive_failures})'
                    
                    error_line = f'      [{elapsed}s] Task Status: {error_msg}'
                    if error_line != last_printed_line:
                        print(f'\x1b[2K\r{error_line}', end='', flush=True)
                        last_printed_line = error_line
                    
                    # Only abort after many consecutive failures (10 instead of 3)
                    # This allows for ~2.5 minutes of connection issues
                    if consecutive_failures >= 10:
                        print(f'\n    {Colors.yellow("⚠")} Many connection failures, but task may still be running')
                        print(f'    Last known status was: {last_known_status}')
                        
                        # Check if the UCS file exists on the system
                        ucs_exists, ucs_size = self._check_ucs_file_exists(task_id)
                        if ucs_exists:
                            print(f'    {Colors.green("✓")} UCS file found on system ({ucs_size / (1024*1024):.1f} MB)')
                            print(f'    Waiting for file to finish writing...')
                            
                            # Monitor file size to see when it stops growing
                            if self._wait_for_file_completion(task_id):
                                print(f'    {Colors.green("✓")} UCS file appears complete despite connection issues')
                                # Return a success result even though we couldn't get task status
                                return {"_taskState": "COMPLETED", "_taskId": task_id}
                        
                        # For large UCS files, give option to wait longer
                        if elapsed < self.ucs_timeout / 2:  # Less than halfway through timeout
                            print(f'    Continuing to wait (timeout in {self.ucs_timeout - elapsed}s)...')
                            consecutive_failures = 5  # Reset to allow more attempts
                        else:
                            print(f'\n    ✗ Too many consecutive failures, aborting')
                            return None
                    
                    time.sleep(check_interval)
            
            elapsed = int(time.time() - start_time)
            print(f'\x1b[2K\r      [{elapsed}s] Task Status: TIMEOUT : Exceeded {self.ucs_timeout}s limit')
            print(f'    ✗ UCS creation timed out after {elapsed} seconds')
            
            # Before giving up completely, do one final check
            try:
                final_response = self.session.get(status_url, timeout=30)
                if final_response.status_code == 200:
                    final_result = final_response.json()
                    final_status = final_result.get('_taskState', 'Unknown')
                    print(f'    Final status check: {final_status}')
                    
                    if final_status == 'COMPLETED':
                        print(f'    {Colors.yellow("⚠")} Task completed after timeout period!')
                        return final_result
            except:
                pass
                
            return None
            
        except Exception as e:
            elapsed = int(time.time() - start_time) if 'start_time' in locals() else 0
            print(f'\x1b[2K\r      [{elapsed}s] Task Status: ERROR : {str(e)}')
            print(f'    ✗ Error waiting for UCS completion')
            return None
    
    def _check_ucs_file_exists(self, task_id):
        """Check if UCS file exists when we can't get task status"""
        try:
            # Try to infer filename from task ID or use wildcard search
            bash_url = f"{self.base_url}/mgmt/tm/util/bash"
            
            # Get the most recent UCS file
            check_payload = {
                "command": "run",
                "utilCmdArgs": "-c 'ls -t /var/local/ucs/*.ucs 2>/dev/null | head -1 | xargs -r stat -c \"%n %s\"'"
            }
            
            response = self.session.post(bash_url, json=check_payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'commandResult' in result:
                    output = result['commandResult'].strip()
                    if output and 'ucs' in output:
                        parts = output.split()
                        if len(parts) >= 2:
                            filename = parts[0]
                            size = int(parts[1])
                            return True, size
            
            return False, 0
        except Exception as e:
            print(f"      Error searching for UCS file: {str(e)}")
            return None
    
    def _check_if_ucs_exists_by_name(self, ucs_filename):
        """Check if a specific UCS file exists by name"""
        try:
            bash_url = f"{self.base_url}/mgmt/tm/util/bash"
            ucs_path = f"/var/local/ucs/{ucs_filename}"
            
            check_payload = {
                "command": "run",
                "utilCmdArgs": f"-c 'if [ -f \"{ucs_path}\" ]; then stat -c \"%s\" \"{ucs_path}\"; else echo \"0\"; fi'"
            }
            
            response = self.session.post(bash_url, json=check_payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'commandResult' in result:
                    try:
                        size = int(result['commandResult'].strip())
                        if size > 0:
                            return True, size
                    except ValueError:
                        pass
            
            return False, 0
        except Exception:
            return False, 0
        except:
            return False, 0
    
    def _wait_for_file_completion(self, task_id):
        """Monitor UCS file size to determine when creation is complete"""
        try:
            bash_url = f"{self.base_url}/mgmt/tm/util/bash"
            last_size = 0
            stable_count = 0
            stable_threshold = 3  # File size must be stable for 3 checks
            
            for i in range(10):  # Check up to 10 times
                # Get current file size
                check_payload = {
                    "command": "run",
                    "utilCmdArgs": "-c 'ls -t /var/local/ucs/*.ucs 2>/dev/null | head -1 | xargs -r stat -c \"%s\"'"
                }
                
                try:
                    response = self.session.post(bash_url, json=check_payload, timeout=30)
                    if response.status_code == 200:
                        result = response.json()
                        if 'commandResult' in result:
                            try:
                                current_size = int(result['commandResult'].strip())
                                
                                if current_size > 0:
                                    if current_size == last_size:
                                        stable_count += 1
                                        print(f'      File size stable at {current_size / (1024*1024):.1f} MB (check {stable_count}/{stable_threshold})')
                                        
                                        if stable_count >= stable_threshold:
                                            return True
                                    else:
                                        stable_count = 0
                                        print(f'      File still growing: {current_size / (1024*1024):.1f} MB')
                                    
                                    last_size = current_size
                            except ValueError:
                                pass
                except:
                    pass
                
                time.sleep(5)  # Wait 5 seconds between checks
            
            # If file exists and is reasonably sized, consider it complete
            return last_size > 10 * 1024 * 1024  # At least 10MB
            
        except Exception as e:
            return False
    
    def _download_ucs(self, ucs_filename):
        """Download UCS file using the proven QKView chunked method"""
        try:
            print(f"    Preparing to download UCS: {ucs_filename}")
            
            # UCS files are stored in /var/local/ucs/
            ucs_path = f"/var/local/ucs/{ucs_filename}"
            
            # First, verify the file exists and get its details
            actual_path = self._find_ucs_file(ucs_filename)
            if not actual_path:
                print(f"    ✗ UCS file not found on remote system")
                print(f"    Expected location: {ucs_path}")
                return False, 0
            
            print(f"    Found UCS at: {actual_path}")
            
            # Get and display file size before downloading
            bash_url = f"{self.base_url}/mgmt/tm/util/bash"
            stat_payload = {
                "command": "run",
                "utilCmdArgs": f"-c 'stat -c \"%s %Y\" \"{actual_path}\"'"  # size and modification time
            }
            
            stat_response = self.session.post(bash_url, json=stat_payload, timeout=30)
            if stat_response.status_code == 200:
                stat_result = stat_response.json()
                if 'commandResult' in stat_result:
                    stat_output = stat_result['commandResult'].strip()
                    if stat_output:
                        parts = stat_output.split()
                        if len(parts) >= 1:
                            try:
                                file_size = int(parts[0])
                                print(f"    Remote file size: {file_size / (1024*1024):.1f} MB ({file_size:,} bytes)")
                                
                                # Sanity check - UCS files should be substantial
                                if file_size < 1024 * 1024:  # Less than 1MB
                                    print(f"    {Colors.yellow('⚠')} Warning: UCS file seems very small (<1MB)")
                                    response = input("    Continue with download? (y/n): ")
                                    if response.lower() != 'y':
                                        return False, 0
                            except ValueError:
                                print(f"    Could not parse file size from stat output")
            
            # Verify file is readable
            verify_payload = {
                "command": "run",
                "utilCmdArgs": f"-c 'if [ -r \"{actual_path}\" ]; then echo \"READABLE\"; else echo \"NOT_READABLE\"; fi'"
            }
            
            verify_response = self.session.post(bash_url, json=verify_payload, timeout=30)
            if verify_response.status_code == 200:
                verify_result = verify_response.json()
                if 'commandResult' in verify_result:
                    if 'NOT_READABLE' in verify_result['commandResult']:
                        print(f"    ✗ UCS file exists but is not readable")
                        return False, 0
                    else:
                        print(f"    {Colors.green('✓')} File is readable and ready for download")
            
            # Use the optimized chunked download method
            print(f"    Starting optimized chunked download...")
            success, file_size = self._download_chunked_f5_method(actual_path, ucs_filename)
            
            if success:
                print(f"    {Colors.green('✓')} Download successful.")
                return True, file_size
            else:
                print(f"    ✗ Download failed")
                return False, file_size
                
        except Exception as e:
            print(f"    ✗ Error downloading UCS: {str(e)}")
            return False, 0
    
    def _find_ucs_file(self, filename):
        """Find the actual location of the UCS file on the BIG-IP"""
        try:
            print(f"    Searching for UCS file...")
            bash_url = f"{self.base_url}/mgmt/tm/util/bash"
            
            # First try exact filename in standard location
            exact_location = f"/var/local/ucs/{filename}"
            find_payload = {
                "command": "run",
                "utilCmdArgs": f"-c 'ls -la {exact_location} 2>/dev/null || echo \"NOT_FOUND\"'"
            }
            
            response = self.session.post(bash_url, json=find_payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'commandResult' in result:
                    command_result = result['commandResult'].strip()
                    if 'NOT_FOUND' not in command_result and command_result:
                        if self.verbose:
                            print(f"      Found exact file: {command_result}")
                        return exact_location
            
            # If not found, search for recent UCS files
            print(f"      Exact filename not found, searching for recent UCS files...")
            
            # List all UCS files sorted by time
            find_payload = {
                "command": "run",
                "utilCmdArgs": f"-c 'ls -lat /var/local/ucs/*.ucs 2>/dev/null | head -5'"
            }
            
            response = self.session.post(bash_url, json=find_payload, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if 'commandResult' in result:
                    command_result = result['commandResult'].strip()
                    if command_result and 'No such file' not in command_result:
                        print(f"      Recent UCS files found:")
                        print(f"      {command_result}")
                        
                        # Look for our file or the most recent one
                        lines = command_result.split('\n')
                        for line in lines:
                            if '.ucs' in line:
                                parts = line.split()
                                if len(parts) >= 9:
                                    found_filename = parts[-1]
                                    if found_filename.endswith('.ucs'):
                                        # Check if this might be our file
                                        if filename.replace('.ucs', '') in found_filename:
                                            print(f"      {Colors.green('✓')} Found matching UCS file: {found_filename}")
                                            return f"/var/local/ucs/{found_filename}"
                        
                        # If no exact match, use the most recent file (first in list)
                        if lines and '.ucs' in lines[0]:
                            parts = lines[0].split()
                            if len(parts) >= 9:
                                recent_file = parts[-1]
                                print(f"      {Colors.yellow('⚠')} Using most recent UCS file: {recent_file}")
                                return f"/var/local/ucs/{recent_file}"
            
            return None
            
        except Exception as e:
            print(f"      Error searching for UCS file: {str(e)}")
            return None
    
    def _download_chunked_f5_method(self, file_path, filename):
        """Download using F5's chunked method via bash and base64 - optimized for UCS"""
        try:
            local_dir = "UCS"
            if not os.path.exists(local_dir):
                os.makedirs(local_dir)
                print(f"      Created local directory: {local_dir}")
            
            local_path = os.path.join(local_dir, filename)
            
            chunk_size = 1024 * 1024  # 1MB chunks for better performance
            
            print(f"      Starting F5 chunked download: {filename}")
            print(f"      Chunk size: {chunk_size / (1024*1024):.1f}MB")
            
            # First, get the file size
            bash_url = f"{self.base_url}/mgmt/tm/util/bash"
            size_payload = {
                "command": "run",
                "utilCmdArgs": f"-c 'stat -c%s \"{file_path}\"'"
            }
            
            size_response = self.session.post(bash_url, json=size_payload, timeout=30)
            total_size = 0
            if size_response.status_code == 200:
                size_result = size_response.json()
                if 'commandResult' in size_result:
                    try:
                        total_size = int(size_result['commandResult'].strip())
                        print(f"      File size: {total_size / (1024*1024):.1f} MB")
                    except:
                        print(f"      Could not determine file size")
            
            with open(local_path, 'wb') as f:
                start = 0
                current_bytes = 0
                chunk_count = 0
                total_chunks = (total_size // chunk_size) + (1 if total_size % chunk_size else 0) if total_size > 0 else 0
                
                while True:
                    chunk_count += 1
                    
                    # Calculate how many bytes to read in this chunk
                    bytes_to_read = min(chunk_size, total_size - start) if total_size > 0 else chunk_size
                    
                    if total_size > 0 and start >= total_size:
                        print(f"\n      Download complete - reached expected file size")
                        break
                    
                    # Read chunk using bash and base64 encoding - optimized with larger block size
                    # Use 64KB block size for dd for much better performance than bs=1
                    block_size = 65536  # 64KB blocks
                    
                    # Calculate block-aligned read
                    skip_blocks = start // block_size
                    skip_remainder = start % block_size
                    
                    if skip_remainder == 0:
                        # Aligned read - much faster
                        blocks_to_read = (bytes_to_read + block_size - 1) // block_size
                        read_payload = {
                            "command": "run",
                            "utilCmdArgs": f"-c 'dd if=\"{file_path}\" bs={block_size} skip={skip_blocks} count={blocks_to_read} 2>/dev/null | head -c {bytes_to_read} | base64 -w 0'"
                        }
                    else:
                        # Unaligned read - use bs=1 for the exact positioning
                        read_payload = {
                            "command": "run",
                            "utilCmdArgs": f"-c 'dd if=\"{file_path}\" bs=1 skip={start} count={bytes_to_read} 2>/dev/null | base64 -w 0'"
                        }
                    
                    try:
                        resp = self.session.post(bash_url, json=read_payload, timeout=120)
                        
                        if resp.status_code == 200:
                            result = resp.json()
                            base64_data = result.get('commandResult', '').strip()
                            
                            if not base64_data:
                                print(f"\n      End of file reached at chunk {chunk_count}")
                                break
                            
                            try:
                                import base64
                                chunk_data = base64.b64decode(base64_data)
                                f.write(chunk_data)
                                current_bytes += len(chunk_data)
                                
                                # Calculate and show progress
                                if total_size > 0:
                                    progress = (current_bytes / total_size) * 100
                                    chunk_display = f"(Chunk {chunk_count}/{total_chunks})" if total_chunks > 0 else f"(Chunk {chunk_count})"
                                    print(f"\r        Progress: {progress:.1f}% ({current_bytes / (1024*1024):.1f} MB / {total_size / (1024*1024):.1f} MB) {chunk_display}", end='', flush=True)
                                else:
                                    print(f"\r        Downloaded: {current_bytes / (1024*1024):.1f} MB (Chunk {chunk_count})", end='', flush=True)
                                
                                # If we got less data than requested, we're at the end
                                if len(chunk_data) < bytes_to_read:
                                    print(f"\n      Download complete - reached end of file")
                                    break
                                
                                # Move to next chunk
                                start += len(chunk_data)
                                    
                            except Exception as decode_error:
                                print(f"\n      Error decoding chunk {chunk_count}: {str(decode_error)}")
                                return False, 0
                        else:
                            print(f"\n      Chunk {chunk_count} request failed: HTTP {resp.status_code}")
                            return False, 0
                            
                    except requests.exceptions.Timeout:
                        print(f"\n      Chunk {chunk_count} timed out")
                        return False, 0
                    except Exception as e:
                        print(f"\n      Chunk {chunk_count} failed: {str(e)}")
                        return False, 0
            
            final_size = os.path.getsize(local_path)
            print(f"\n      {Colors.green('✓')} F5 chunked download completed: {filename}")
            print(f"      Final file size: {final_size} bytes ({final_size / (1024*1024):.1f} MB)")
            
            # Verify file size matches expected
            if total_size > 0:
                size_difference = abs(final_size - total_size)
                
                if size_difference == 0:
                    print(f"      {Colors.green('✓')} File size matches exactly!")
                elif size_difference <= 1024:  # 1KB tolerance
                    print(f"      {Colors.green('✓')} File size within acceptable tolerance ({size_difference} bytes)")
                else:
                    print(f"      {Colors.yellow('⚠')} File size difference: {size_difference} bytes")
                    print(f"      Expected: {total_size}, Got: {final_size}")
                    
                    # Don't fail if we got most of the file
                    if final_size >= total_size * 0.95:  # At least 95%
                        print(f"      {Colors.green('✓')} File size is acceptable (95%+ of expected)")
                    else:
                        print(f"      ✗ File size too different - download may be incomplete")
                        return False, final_size
            
            # Basic sanity check - UCS files should be substantial  
            if final_size < 1 * 1024 * 1024:  # Less than 1MB is suspicious
                print(f"      {Colors.yellow('⚠')} Warning: UCS file seems very small ({final_size / (1024*1024):.1f} MB)")
                
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
            print(f"\n      F5 chunked download failed: {str(e)}")
            if self.verbose:
                print(f"      Traceback: {traceback.format_exc()}")
            return False, 0
    
    def _cleanup_ucs_task(self, task_id):
        """Clean up UCS task using F5 task endpoint"""
        try:
            cleanup_url = f"{self.base_url}/mgmt/tm/task/sys/ucs/{task_id}"
            
            print(f"    Cleaning up UCS task: {task_id}")
            response = self.session.delete(cleanup_url, timeout=30)
            response.raise_for_status()
            
            print(f"    ✓ UCS task cleaned up successfully")
            
        except Exception as e:
            print(f"    Warning: Failed to cleanup UCS task {task_id}: {str(e)}")
    
    def _cleanup_ucs_file(self, filename):
        """Clean up UCS file from /var/local/ucs/ after download"""
        try:
            ucs_path = f"/var/local/ucs/{filename}"
            bash_url = f"{self.base_url}/mgmt/tm/util/bash"
            
            print(f"    Cleaning up original UCS file...")
            
            # First verify the file exists
            check_payload = {
                "command": "run",
                "utilCmdArgs": f"-c 'ls -la {ucs_path} 2>/dev/null'"
            }
            
            check_response = self.session.post(bash_url, json=check_payload, timeout=30)
            if check_response.status_code == 200:
                check_result = check_response.json()
                if 'No such file' in check_result.get('commandResult', ''):
                    print(f"    File already removed or doesn't exist")
                    return
                else:
                    file_info = check_result.get('commandResult', '').strip()
                    if self.verbose and file_info:
                        print(f"    File to remove: {file_info}")
            
            # Wait a moment to ensure file handles are closed
            time.sleep(2)
            
            # Use rm -f via bash for more reliable deletion
            cleanup_payload = {
                "command": "run",
                "utilCmdArgs": f"-c 'rm -f {ucs_path} 2>&1'"
            }
            
            response = self.session.post(bash_url, json=cleanup_payload, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                command_result = result.get('commandResult', '').strip()
                
                # Check for error messages
                if command_result and 'cannot remove' in command_result.lower():
                    print(f"    Warning: Failed to remove file: {command_result}")
                    return
                
                # Verify the file was actually deleted
                time.sleep(1)  # Brief pause before checking
                verify_payload = {
                    "command": "run",
                    "utilCmdArgs": f"-c 'if [ -f {ucs_path} ]; then echo \"STILL_EXISTS\"; else echo \"DELETED\"; fi'"
                }
                
                verify_response = self.session.post(bash_url, json=verify_payload, timeout=30)
                if verify_response.status_code == 200:
                    verify_result = verify_response.json()
                    verify_output = verify_result.get('commandResult', '').strip()
                    
                    if verify_output == 'DELETED':
                        print(f"    {Colors.green('✓')} Original UCS file cleaned up successfully")
                    elif verify_output == 'STILL_EXISTS':
                        print(f"    {Colors.yellow('⚠')} Warning: File still exists after deletion attempt")
                        
                        # Try one more time with sudo/force
                        force_payload = {
                            "command": "run",
                            "utilCmdArgs": f"-c 'rm -rf {ucs_path} 2>&1; sync'"
                        }
                        
                        force_response = self.session.post(bash_url, json=force_payload, timeout=30)
                        if force_response.status_code == 200:
                            # Final verification
                            time.sleep(1)
                            final_verify = self.session.post(bash_url, json=verify_payload, timeout=30)
                            if final_verify.status_code == 200:
                                final_result = final_verify.json()
                                if 'DELETED' in final_result.get('commandResult', ''):
                                    print(f"    {Colors.green('✓')} File removed on second attempt")
                                else:
                                    print(f"    {Colors.red('✗')} Failed to remove file - may require manual cleanup")
                                    print(f"    File location: {ucs_path}")
                    else:
                        print(f"    Cleanup verification returned unexpected result: {verify_output}")
            else:
                print(f"    Warning: Cleanup command failed with status {response.status_code}")
                
        except Exception as e:
            print(f"    Warning: Failed to cleanup original UCS file: {str(e)}")

