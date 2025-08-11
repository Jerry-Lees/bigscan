#!/usr/bin/env python3
"""
BIG-IP Device Information Extractor

This script connects to F5 BIG-IP devices and extracts comprehensive system information
including hostname, serial number, registration key, software version, hotfixes, and more.
The data is exported to a CSV file for easy analysis.

Enhanced QKView Feature:
- Uses F5's official autodeploy endpoint for reliable QKView generation
- Proper asynchronous task monitoring
- Downloads QKViews to local 'QKViews' directory
- Automatic cleanup of remote files after download
- Enhanced error handling and progress reporting

Enhanced UCS Feature:
- Creates UCS (User Configuration Set) backup files on remote BIG-IP devices
- Downloads UCS files to local 'UCS' directory
- UCS files contain complete configuration backups including certificates and keys
- Configurable timeout and cleanup options

Requirements:
    pip install requests urllib3

Usage:
    python bigscan.py [--user USERNAME] [--pass PASSWORD] [--out FILENAME] [--in INPUT_CSV] [--qkview] [--ucs] [--help]
    
Examples:
    python bigscan.py                                              # Interactive mode
    python bigscan.py --user admin                                 # Specify user, prompt for password  
    python bigscan.py --user admin --pass mypassword               # Specify both credentials
    python bigscan.py --user admin --out my_devices.csv            # Specify output file
    python bigscan.py -u admin -p mypass -o device_report.csv      # Short form options
    python bigscan.py --in devices.csv --out results.csv           # Bulk processing from CSV
    python bigscan.py --in devices.csv --user admin                # CSV with fallback credentials
    python bigscan.py --in devices.csv --qkview --out results.csv  # Include QKView creation
    python bigscan.py --in devices.csv --ucs --out results.csv     # Include UCS backup creation
    python bigscan.py -q --qkview-timeout 1200 --in devices.csv    # QKView with 20min timeout
    python bigscan.py --ucs --ucs-timeout 900 --in devices.csv     # UCS with 15min timeout
    python bigscan.py --qkview --ucs --in devices.csv              # Both QKView and UCS
"""

import argparse
import os
from modules.colors import Colors
from modules.bigip_extractor import BigIPInfoExtractor
from modules.csv_handler import write_to_csv, read_devices_from_csv
from modules.auth_handler import get_credentials_for_device
from modules.device_processor import process_devices_from_file, process_devices_interactively


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
    python %(prog)s --in devices.csv --ucs --out results.csv     # Include UCS backup creation
    python %(prog)s -q --qkview-timeout 1200 --in devices.csv    # QKView with 20min timeout
    python %(prog)s --ucs --ucs-timeout 900 --in devices.csv     # UCS with 15min timeout
    python %(prog)s --qkview --ucs --in devices.csv              # Both QKView and UCS
    python %(prog)s --qkview --ucs --no-delete --in devices.csv  # Both with no remote cleanup
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
    parser.add_argument('--ucs',
                       action='store_true',
                       help='Create and download UCS backup from each device')
    parser.add_argument('--ucs-timeout',
                       type=int,
                       default=900,
                       help='Timeout for UCS creation in seconds (default: 900)')
    parser.add_argument('--no-qkview',
                       action='store_true',
                       help='Disable QKView creation (default behavior)')
    parser.add_argument('--no-delete',
                       action='store_true',
                       help='Do not delete QKView/UCS files from remote system after download (debugging option)')
    parser.add_argument('-vvv', '--verbose',
                       action='store_true',
                       help='Enable verbose debug output')
    
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
        if args.no_delete:
            print("Remote QKView cleanup DISABLED - files will be left on BIG-IP devices")
        else:
            print("Remote QKView files will be cleaned up after successful download")
        print("This will take additional time per device\n")
        
        # Create local QKViews directory if it doesn't exist
        qkviews_dir = "QKViews"
        if not os.path.exists(qkviews_dir):
            os.makedirs(qkviews_dir)
            print(f"Created local directory: {qkviews_dir}")
        else:
            print(f"Using existing directory: {qkviews_dir}")
        print("")
    
    # UCS information
    if args.ucs:
        print("UCS backup creation enabled")
        print(f"UCS timeout set to {args.ucs_timeout} seconds ({args.ucs_timeout/60:.1f} minutes)")
        print("UCS files will be downloaded to the 'UCS' directory")
        if args.no_delete:
            print("Remote UCS cleanup DISABLED - files will be left on BIG-IP devices")
        else:
            print("Remote UCS files will be cleaned up after successful download")
        print("This will take additional time per device\n")
        
        # Create local UCS directory if it doesn't exist
        ucs_dir = "UCS"
        if not os.path.exists(ucs_dir):
            os.makedirs(ucs_dir)
            print(f"Created local directory: {ucs_dir}")
        else:
            print(f"Using existing directory: {ucs_dir}")
        print("")
    
    # Warning if both QKView and UCS are enabled
    if args.qkview and args.ucs:
        print(f"{Colors.yellow('⚠')} Both QKView and UCS creation enabled - this will significantly increase processing time")
        print("Consider running separately if processing many devices\n")
    
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
        
        if args.ucs:
            ucs_count = sum(1 for device in devices_info if device.get('ucs_downloaded') == 'Yes')
            print(f"UCS backups downloaded: {ucs_count}/{len(devices_info)}")
            if ucs_count > 0:
                print(f"UCS files saved in: ./UCS/")
    else:
        print("No device information collected.")
        # Still create an empty CSV file with headers
        write_to_csv([], args.out)
        print(f"Empty CSV file created: {args.out}")


if __name__ == "__main__":
    main()

