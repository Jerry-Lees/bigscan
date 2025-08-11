"""
Device processing utilities for handling single and multiple device operations
"""

import getpass
from .colors import Colors
from .csv_handler import read_devices_from_csv
from .auth_handler import get_credentials_for_device
from .bigip_extractor import BigIPInfoExtractor


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
    if args.ucs:
        print("UCS backup creation and download enabled")
        print(f"UCS timeout: {args.ucs_timeout} seconds ({args.ucs_timeout/60:.1f} minutes)")
    if args.qkview and args.ucs:
        print(f"{Colors.yellow('⚠')} Both QKView and UCS enabled - processing will take longer")
    print("=" * 50)
    
    for i, device in enumerate(devices, 1):
        device_header = f"[{i}/{len(devices)}] Processing device: {device['ip']}"
        print(f"\n{Colors.blue(device_header)}")
        
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
            qkview_timeout=args.qkview_timeout,
            create_ucs=args.ucs,
            ucs_timeout=args.ucs_timeout,
            no_delete=args.no_delete,
            verbose=args.verbose
        )
        
        if extractor.extract_all_info():
            devices_info.append(extractor.device_info)
            print(f"  {Colors.green('✓')} Successfully extracted information from {device['ip']}")
            
            # Display brief summary
            hostname = extractor.device_info.get('hostname', 'N/A')
            version = extractor.device_info.get('active_version', 'N/A')
            qkview_status = extractor.device_info.get('qkview_downloaded', 'N/A')
            ucs_status = extractor.device_info.get('ucs_downloaded', 'N/A')
            print(f"    Hostname: {hostname}, Version: {version}")
            if args.qkview:
                print(f"    QKView: {qkview_status}")
            if args.ucs:
                print(f"    UCS: {ucs_status}")
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
                        qkview_timeout=args.qkview_timeout,
                        create_ucs=args.ucs,
                        ucs_timeout=args.ucs_timeout,
                        no_delete=args.no_delete,
                        verbose=args.verbose
                    )
                    if extractor.extract_all_info():
                        devices_info.append(extractor.device_info)
                        print(f"  {Colors.green('✓')} Successfully extracted information from {device['ip']} (retry)")
                        hostname = extractor.device_info.get('hostname', 'N/A')
                        version = extractor.device_info.get('active_version', 'N/A')
                        qkview_status = extractor.device_info.get('qkview_downloaded', 'N/A')
                        ucs_status = extractor.device_info.get('ucs_downloaded', 'N/A')
                        print(f"    Hostname: {hostname}, Version: {version}")
                        if args.qkview:
                            print(f"    QKView: {qkview_status}")
                        if args.ucs:
                            print(f"    UCS: {ucs_status}")
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
            qkview_timeout=args.qkview_timeout,
            create_ucs=args.ucs,
            ucs_timeout=args.ucs_timeout,
            no_delete=args.no_delete,
            verbose=args.verbose
        )
        
        if extractor.extract_all_info():
            devices_info.append(extractor.device_info)
            print(f"{Colors.green('✓')} Successfully extracted information from {host}")
            
            # Display summary
            print("\nDevice Summary:")
            print(f"  Hostname: {extractor.device_info.get('hostname', 'N/A')}")
            print(f"  Serial: {extractor.device_info.get('serial_number', 'N/A')}")
            print(f"  Version: {extractor.device_info.get('active_version', 'N/A')}")
            print(f"  Emergency Hotfixes: {extractor.device_info.get('emergency_hotfixes', 'None')}")
            if args.qkview:
                qkview_status = extractor.device_info.get('qkview_downloaded', 'N/A')
                if qkview_status == 'Yes':
                    print(f"  QKView: {Colors.green('✓')} {qkview_status}")
                else:
                    print(f"  QKView: {qkview_status}")
            if args.ucs:
                ucs_status = extractor.device_info.get('ucs_downloaded', 'N/A')
                if ucs_status == 'Yes':
                    print(f"  UCS: {Colors.green('✓')} {ucs_status}")
                else:
                    print(f"  UCS: {ucs_status}")
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
                        qkview_timeout=args.qkview_timeout,
                        create_ucs=args.ucs,
                        ucs_timeout=args.ucs_timeout,
                        no_delete=args.no_delete,
                        verbose=args.verbose
                    )
                    if extractor.extract_all_info():
                        devices_info.append(extractor.device_info)
                        print(f"{Colors.green('✓')} Successfully extracted information from {host}")
                        
                        # Display summary
                        print("\nDevice Summary:")
                        print(f"  Hostname: {extractor.device_info.get('hostname', 'N/A')}")
                        print(f"  Serial: {extractor.device_info.get('serial_number', 'N/A')}")
                        print(f"  Version: {extractor.device_info.get('active_version', 'N/A')}")
                        print(f"  Emergency Hotfixes: {extractor.device_info.get('emergency_hotfixes', 'None')}")
                        if args.qkview:
                            qkview_status = extractor.device_info.get('qkview_downloaded', 'N/A')
                            if qkview_status == 'Yes':
                                print(f"  QKView: {Colors.green('✓')} {qkview_status}")
                            else:
                                print(f"  QKView: {qkview_status}")
                        if args.ucs:
                            ucs_status = extractor.device_info.get('ucs_downloaded', 'N/A')
                            if ucs_status == 'Yes':
                                print(f"  UCS: {Colors.green('✓')} {ucs_status}")
                            else:
                                print(f"  UCS: {ucs_status}")
                    else:
                        print(f"Authentication failed again for {host}")
        
        print()
        
        # Ask if user wants to add another device
        another = input("Add another device? (y/n): ").strip().lower()
        if another not in ['y', 'yes']:
            break
    
    return devices_info

