"""
Authentication handling utilities for F5 BIG-IP devices
"""

import getpass
import requests


class BigIPAuthHandler:
    """Handles authentication for F5 BIG-IP devices"""
    
    def __init__(self, host, username, password, session=None, verbose=False):
        """Initialize authentication handler"""
        self.host = host
        self.username = username
        self.password = password
        self.token = None
        self.session = session or requests.Session()
        self.session.verify = False
        self.base_url = f"https://{self.host}"
        self.token_timeout = 1200  # 20 minutes default token timeout
        self.verbose = verbose
    
    def get_auth_token(self):
        """Get authentication token from BIG-IP"""
        try:
            if self.verbose:
                print(f"Getting auth token from {self.host}...")
            else:
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
            
            if self.verbose:
                print(f"Token timeout extended to {self.token_timeout} seconds")
            
        except Exception as e:
            print(f"Warning: Could not extend token timeout for {self.host}: {str(e)}")
    
    def logout(self):
        """Logout and invalidate the authentication token"""
        try:
            if not self.token:
                return
            
            logout_url = f"{self.base_url}/mgmt/shared/authz/tokens/{self.token}"
            self.session.delete(logout_url, timeout=30)
            
            if self.verbose:
                print(f"Successfully logged out from {self.host}")
            
            # Clean up session
            self.token = None
            if 'X-F5-Auth-Token' in self.session.headers:
                del self.session.headers['X-F5-Auth-Token']
            
        except Exception as e:
            print(f"Warning: Could not logout cleanly from {self.host}: {str(e)}")
    
    def is_authenticated(self):
        """Check if currently authenticated"""
        return self.token is not None
    
    def get_token(self):
        """Get the current authentication token"""
        return self.token
    
    def get_session(self):
        """Get the authenticated session"""
        return self.session


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
