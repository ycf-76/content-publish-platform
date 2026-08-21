"""Info Command - Show plugin details."""

import argparse
import json
import os
from .base import BaseCommand


class InfoCommand(BaseCommand):
    """Show plugin details."""
    
    name = "info"
    help = "Show plugin details"
    aliases = ['show']
    
    def add_arguments(self, parser: argparse.ArgumentParser):
        parser.add_argument(
            'plugin_id',
            type=str,
            nargs='?',
            default=None,
            help='Plugin ID (default: current directory)'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        self.verbose = getattr(args, 'verbose', 0)
        
        # Look for plugin.json
        paths = ['.', 'plugins']
        if args.plugin_id:
            paths.insert(0, os.path.join('plugins', args.plugin_id))
        
        for path in paths:
            plugin_file = os.path.join(path, 'plugin.json')
            if os.path.exists(plugin_file):
                with open(plugin_file, 'r') as f:
                    data = json.load(f)
                
                print(f"\n{'='*60}")
                print(f"Plugin: {data.get('name', 'Unknown')}")
                print(f"{'='*60}")
                
                for key, value in data.items():
                    if key != 'config_schema':
                        print(f"{key:<20}: {value}")
                
                return 0
        
        self.print_error("Plugin not found")
        return 1