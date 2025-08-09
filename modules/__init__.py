"""
BIG-IP Device Information Extractor Modules

This package contains modular components for the BIG-IP device information extraction tool.
"""

from .colors import Colors
from .bigip_extractor import BigIPInfoExtractor
from .csv_handler import write_to_csv, read_devices_from_csv
from .auth_handler import get_credentials_for_device
from .device_processor import process_devices_from_file, process_devices_interactively
from .qkview_handler import QKViewHandler
from .support_lifecycle import SupportLifecycleProcessor, get_support_processor

__all__ = [
    'Colors',
    'BigIPInfoExtractor',
    'write_to_csv',
    'read_devices_from_csv',
    'get_credentials_for_device',
    'process_devices_from_file',
    'process_devices_interactively',
    'QKViewHandler',
    'SupportLifecycleProcessor',
    'get_support_processor'
]

__version__ = '2.0.0'
__author__ = 'F5 BIG-IP Scanner'
__description__ = 'Modular F5 BIG-IP device information extraction tool'
