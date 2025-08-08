"""
Color utilities for console output
"""

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    LIGHT_BLUE = '\033[38;5;117m'
    ENDC = '\033[0m'  # End color
    
    @staticmethod
    def green(text):
        return f"{Colors.GREEN}{text}{Colors.ENDC}"
    
    @staticmethod
    def yellow(text):
        return f"{Colors.YELLOW}{text}{Colors.ENDC}"
    
    @staticmethod
    def red(text):
        return f"{Colors.RED}{text}{Colors.ENDC}"
    
    @staticmethod
    def blue(text):
        return f"{Colors.BLUE}{text}{Colors.ENDC}"
    
    @staticmethod
    def cyan(text):
        return f"{Colors.CYAN}{text}{Colors.ENDC}"
    
    @staticmethod
    def magenta(text):
        return f"{Colors.MAGENTA}{text}{Colors.ENDC}"
    
    @staticmethod
    def light_blue(text):
        return f"{Colors.LIGHT_BLUE}{text}{Colors.ENDC}"

