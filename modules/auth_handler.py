"""
Authentication handling utilities
"""

import getpass


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

