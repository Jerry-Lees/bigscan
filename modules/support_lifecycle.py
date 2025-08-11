"""
F5 Support Lifecycle Module

Provides software lifecycle information including End of Life (EOL), End of Software 
Development (EoSD), and End of Technical Support (EoTS) dates for F5 BIG-IP software.

Data source: K5903: BIG-IP software support policy
Last updated: August 8, 2025
URL: https://my.f5.com/manage/s/article/K5903

Note: This data should be regularly updated as F5 publishes new support policies.
Always refer to the official F5 documentation for the most current information.
"""

from datetime import datetime, date
import re
from typing import Dict, Optional, Tuple, List
from .colors import Colors


class SupportLifecycleProcessor:
    """Processes F5 BIG-IP software support lifecycle information"""
    
    def __init__(self, verbose=False):
        self.verbose = verbose
        self.data_last_updated = "2025-08-08"
        self.source_url = "https://my.f5.com/manage/s/article/K5903"
        self._load_support_data()
    
    def _load_support_data(self):
        """Load F5 software support lifecycle data"""
        
        # Currently supported versions (as of August 8, 2025)
        self.supported_versions = {
            "17.5.0": {
                "type": "Long-Term Stability Release",
                "first_customer_ship": "2025-02-27",
                "end_of_software_development": "2029-01-01", 
                "end_of_technical_support": "2029-01-01",
                "latest_maintenance": "17.5.1",
                "support_phase": "Standard Support",
                "notes": "Longer than three-year Standard Support phase"
            },
            "17.5.1": {
                "type": "Long-Term Stability Release", 
                "first_customer_ship": "2025-02-27",
                "end_of_software_development": "2029-01-01",
                "end_of_technical_support": "2029-01-01", 
                "latest_maintenance": "17.5.1",
                "support_phase": "Standard Support",
                "notes": "Latest maintenance release of 17.5.x"
            },
            "17.1.0": {
                "type": "Long-Term Stability Release",
                "first_customer_ship": "2023-03-14",
                "end_of_software_development": "2027-03-31",
                "end_of_technical_support": "2027-03-31",
                "latest_maintenance": "17.1.2", 
                "support_phase": "Standard Support",
                "notes": "Four-year support cycle"
            },
            "17.1.1": {
                "type": "Long-Term Stability Release",
                "first_customer_ship": "2023-03-14", 
                "end_of_software_development": "2027-03-31",
                "end_of_technical_support": "2027-03-31",
                "latest_maintenance": "17.1.2",
                "support_phase": "Standard Support", 
                "notes": "Maintenance release"
            },
            "17.1.2": {
                "type": "Long-Term Stability Release",
                "first_customer_ship": "2023-03-14",
                "end_of_software_development": "2027-03-31", 
                "end_of_technical_support": "2027-03-31",
                "latest_maintenance": "17.1.2",
                "support_phase": "Standard Support",
                "notes": "Latest maintenance release of 17.1.x"
            }
        }
        
        # EOL versions (abbreviated for space)
        self.eol_versions = {
            "16.1.0": {
                "type": "Long-Term Stability Release", 
                "end_of_software_development": "2025-07-31",
                "end_of_technical_support": "2025-07-31",
                "support_phase": "End of Life", 
                "notes": "Four-year LTS lifecycle"
            },
            "16.1.1": {
                "type": "Long-Term Stability Release",
                "end_of_software_development": "2025-07-31", 
                "end_of_technical_support": "2025-07-31",
                "support_phase": "End of Life",
                "notes": "Maintenance release"
            },
            "16.1.2": {
                "type": "Long-Term Stability Release",
                "end_of_software_development": "2025-07-31",
                "end_of_technical_support": "2025-07-31", 
                "support_phase": "End of Life", 
                "notes": "Maintenance release"
            },
            "15.1.0": {
                "type": "Long-Term Stability Release",
                "end_of_software_development": "2024-12-31",
                "end_of_technical_support": "2024-12-31",
                "support_phase": "End of Life", 
                "notes": "Five-year LTS lifecycle"
            },
            "14.1.0": {
                "type": "Long-Term Stability Release",
                "end_of_software_development": "2023-12-31",
                "end_of_technical_support": "2023-12-31",
                "support_phase": "End of Life", 
                "notes": "Five-year LTS lifecycle"
            },
            "13.1.0": {
                "type": "Long-Term Stability Release",
                "end_of_software_development": "2022-12-31",
                "end_of_technical_support": "2023-12-31", 
                "support_phase": "End of Life",
                "notes": "Five-year LTS lifecycle with extended EoTS"
            }
        }
        
        # Create combined lookup dictionary
        self.all_versions = {}
        self.all_versions.update(self.supported_versions)
        self.all_versions.update(self.eol_versions)
        
        if self.verbose:
            print(f"Loaded support data for {len(self.all_versions)} software versions")
    
    def get_version_support_info(self, version: str) -> Dict:
        """Get comprehensive support information for a specific version"""
        normalized_version = self._normalize_version(version)
        version_info = self.all_versions.get(normalized_version)
        
        if not version_info:
            version_info = self._find_branch_match(normalized_version)
        
        if not version_info:
            return {
                "version": version,
                "found": False,
                "support_status": "Unknown",
                "message": f"Version {version} not found in support database",
                "recommendation": "Verify version number and check F5 documentation",
                "urgency": "Unknown",
                "data_source": self.source_url,
                "data_last_updated": self.data_last_updated
            }
        
        status_info = self._calculate_support_status(version_info)
        
        result = {
            "version": version,
            "normalized_version": normalized_version,
            "found": True,
            "type": version_info.get("type", "Unknown"),
            "support_phase": version_info.get("support_phase", "Unknown"),
            "support_status": status_info["current_status"],
            "status_color": status_info["status_color"],
            "first_customer_ship": version_info.get("first_customer_ship"),
            "end_of_software_development": version_info.get("end_of_software_development"),
            "end_of_technical_support": version_info.get("end_of_technical_support"),
            "latest_maintenance": version_info.get("latest_maintenance"),
            "days_until_eosd": status_info["days_until_eosd"],
            "days_until_eots": status_info["days_until_eots"],
            "recommendation": status_info["recommendation"],
            "urgency": status_info["urgency"],
            "notes": version_info.get("notes", ""),
            "data_source": self.source_url,
            "data_last_updated": self.data_last_updated
        }
        
        return result
    
    def _normalize_version(self, version: str) -> str:
        """Normalize version string for consistent lookup"""
        if not version:
            return ""
        
        version = version.strip()
        version = re.sub(r'^(BIG-IP|TMOS)\s*', '', version, flags=re.IGNORECASE)
        version = re.sub(r'^\s*v\.?\s*', '', version, flags=re.IGNORECASE)
        
        parts = version.split('.')
        
        if len(parts) >= 3:
            normalized = f"{parts[0]}.{parts[1]}.{parts[2]}"
        elif len(parts) == 2:
            normalized = f"{parts[0]}.{parts[1]}.0"
        else:
            normalized = version
        
        return normalized
    
    def _find_branch_match(self, version: str) -> Optional[Dict]:
        """Find support info by matching version branch patterns"""
        parts = version.split('.')
        if len(parts) < 2:
            return None
        
        major_minor = f"{parts[0]}.{parts[1]}"
        
        for ver, info in self.all_versions.items():
            if ver.startswith(major_minor + "."):
                branch_info = info.copy()
                branch_info["notes"] = f"Branch match from {ver}. " + branch_info.get("notes", "")
                return branch_info
        
        return None
    
    def _calculate_support_status(self, version_info: Dict) -> Dict:
        """Calculate current support status and recommendations"""
        today = date.today()
        
        eosd_date = self._parse_date(version_info.get("end_of_software_development"))
        eots_date = self._parse_date(version_info.get("end_of_technical_support"))
        
        days_until_eosd = None
        days_until_eots = None
        
        if eosd_date:
            days_until_eosd = (eosd_date - today).days
        
        if eots_date:
            days_until_eots = (eots_date - today).days
        
        current_status = "Unknown"
        status_color = "gray"
        urgency = "Low"
        recommendation = "No action required"
        
        if version_info.get("support_phase") == "End of Life":
            current_status = "End of Life"
            status_color = "red"
            urgency = "Critical"
            recommendation = "Upgrade immediately - no support available"
        elif eots_date and today > eots_date:
            current_status = "End of Life"
            status_color = "red"
            urgency = "Critical"
            recommendation = "Upgrade immediately - technical support ended"
        elif eosd_date and today > eosd_date:
            current_status = "End of Software Development" 
            status_color = "orange"
            urgency = "High"
            recommendation = "Plan upgrade - no new fixes or hotfixes available"
        elif eots_date and days_until_eots is not None:
            if days_until_eots <= 90:
                current_status = "End of Support Soon"
                status_color = "orange"
                urgency = "High"
                recommendation = f"Upgrade urgently - support ends in {days_until_eots} days"
            elif days_until_eots <= 365:
                current_status = "Support Ending"
                status_color = "yellow"
                urgency = "Medium"
                recommendation = f"Plan upgrade - support ends in {days_until_eots} days"
            else:
                current_status = "Supported"
                status_color = "green"
                urgency = "Low"
                recommendation = "Version is currently supported"
        else:
            current_status = "Supported"
            status_color = "green"
            urgency = "Low"
            recommendation = "Version is currently supported"
        
        return {
            "current_status": current_status,
            "status_color": status_color,
            "days_until_eosd": days_until_eosd,
            "days_until_eots": days_until_eots,
            "urgency": urgency,
            "recommendation": recommendation
        }
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string to date object"""
        if not date_str:
            return None
        
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            if self.verbose:
                print(f"Warning: Could not parse date '{date_str}'")
            return None


def get_support_processor(verbose=False) -> SupportLifecycleProcessor:
    """Factory function to create a SupportLifecycleProcessor instance"""
    return SupportLifecycleProcessor(verbose=verbose)


def get_version_support_status(version: str, verbose=False) -> Dict:
    """Quick function to get support status for a single version"""
    processor = get_support_processor(verbose)
    return processor.get_version_support_info(version)

