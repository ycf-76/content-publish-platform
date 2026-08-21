#!/usr/bin/env python3
"""
Plugin CLI - Main Entry Point
=============================

Command-line interface for plugin development toolkit.
"""

import argparse
import sys
import os
from typing import Optional, List

from . import __version__
from .commands.create import CreateCommand
from .commands.dev import DevCommand
from .commands.test import TestCommand
from .commands.build import BuildCommand
from .commands.publish import PublishCommand
from .commands.list_cmd import ListCommand
from .commands.info import InfoCommand
from .commands.config_cmd import ConfigCommand
from .commands.logs import LogsCommand
from .commands.doctor import DoctorCommand
from .commands.version_cmd import VersionCommand


def create_parser() -> argparse.ArgumentParser:
    """Create main argument parser."""
    
    parser = argparse.ArgumentParser(
        prog='plugin',
        description='Plugin Developer CLI Toolkit - Develop, test, debug and publish plugins',
        epilog='For more information, visit: https://docs.your-platform.com/plugins',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        '-V', '--version',
        action='version',
        version=f'%(prog)s v{__version__}'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='count',
        default=0,
        help='Increase verbosity level (-v for info, -vv for debug)'
    )
    
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default=None,
        help='Path to config file (default: .plugin-config.json)'
    )
    
    # Subparsers for commands
    subparsers = parser.add_subparsers(
        dest='command',
        title='available commands',
        metavar='<command>'
    )
    
    # Register commands
    commands = [
        CreateCommand(),
        DevCommand(),
        TestCommand(),
        BuildCommand(),
        PublishCommand(),
        ListCommand(),
        InfoCommand(),
        ConfigCommand(),
        LogsCommand(),
        DoctorCommand(),
        VersionCommand(),
    ]
    
    for cmd in commands:
        cmd.register(subparsers)
    
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point.
    
    Args:
        argv: Command line arguments (default: sys.argv[1:])
        
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    
    parser = create_parser()
    args = parser.parse_args(argv)
    
    # No command provided
    if not args.command:
        parser.print_help()
        return 0
    
    # Execute command
    try:
        command_instance = get_command_instance(args.command)
        if command_instance:
            return command_instance.execute(args)
        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1
            
    except KeyboardInterrupt:
        print("\nOperation cancelled by user", file=sys.stderr)
        return 130
        
    except Exception as e:
        if args.verbose >= 2:
            import traceback
            traceback.print_exc()
        else:
            print(f"Error: {e}", file=sys.stderr)
        return 1


def get_command_instance(command_name: str):
    """Get command instance by name."""
    
    command_map = {
        'create': CreateCommand,
        'dev': DevCommand,
        'test': TestCommand,
        'build': BuildCommand,
        'publish': PublishCommand,
        'list': ListCommand,
        'ls': ListCommand,
        'info': InfoCommand,
        'show': InfoCommand,
        'config': ConfigCommand,
        'cfg': ConfigCommand,
        'logs': LogsCommand,
        'log': LogsCommand,
        'doctor': DoctorCommand,
        'diag': DoctorCommand,
        'check': DoctorCommand,
        'version': VersionCommand,
        'ver': VersionCommand,
    }
    
    CommandClass = command_map.get(command_name)
    if CommandClass:
        return CommandClass()
    return None


if __name__ == '__main__':
    sys.exit(main())