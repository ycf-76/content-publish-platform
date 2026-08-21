"""
Base Command Class
==================

Abstract base class for all CLI commands.
"""

import argparse
from abc import ABC, abstractmethod
from typing import Optional


class BaseCommand(ABC):
    """Base class for all plugin CLI commands."""
    
    name: str = ""
    help: str = ""
    description: str = ""
    
    def __init__(self):
        self.verbose: int = 0
        self.no_color: bool = False
        self.config_path: Optional[str] = None
    
    def register(self, subparsers: argparse._SubParsersAction):
        """
        Register command with argument parser.
        
        Args:
            subparsers: Subparsers action from main parser
        """
        
        parser = subparsers.add_parser(
            self.name,
            help=self.help,
            description=self.description or self.help,
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        
        # Add command-specific arguments
        self.add_arguments(parser)
        
        # Set execute function
        parser.set_defaults(func=self.execute)
    
    def add_arguments(self, parser: argparse.ArgumentParser):
        """
        Add command-specific arguments.
        
        Override in subclass to add custom arguments.
        
        Args:
            parser: Argument parser for this command
        """
        pass
    
    @abstractmethod
    def execute(self, args: argparse.Namespace) -> int:
        """
        Execute the command.
        
        Args:
            args: Parsed arguments
            
        Returns:
            Exit code (0 for success)
        """
        pass
    
    def print_info(self, message: str):
        """Print info message (blue)."""
        if self.no_color:
            print(message)
        else:
            print(f"\033[94m{message}\033[0m")
    
    def print_success(self, message: str):
        """Print success message (green)."""
        if self.no_color:
            print(message)
        else:
            print(f"\033[92m✓ {message}\033[0m")
    
    def print_warning(self, message: str):
        """Print warning message (yellow)."""
        if self.no_color:
            print(f"WARNING: {message}", file=__import__('sys').stderr)
        else:
            print(f"\033[93m⚠ {message}\033[0m", file=__import__('sys').stderr)
    
    def print_error(self, message: str):
        """Print error message (red)."""
        if self.no_color:
            print(f"ERROR: {message}", file=__import__('sys').stderr)
        else:
            print(f"\033[91m✗ {message}\033[0m", file=__import__('sys').stderr)
    
    def print_debug(self, message: str):
        """Print debug message (gray)."""
        if self.verbose >= 2:
            if self.no_color:
                print(f"[DEBUG] {message}")
            else:
                print(f"\033[90m[DEBUG] {message}\033[0m")