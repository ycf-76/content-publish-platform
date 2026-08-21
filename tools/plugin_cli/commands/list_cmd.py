"""List Command - List local plugins."""

import argparse
import json
import os
from .base import BaseCommand


class ListCommand(BaseCommand):
    """List local plugins."""
    
    name = "list"
    help = "List local plugins"
    aliases = ['ls']
    
    def add_arguments(self, parser: argparse.ArgumentParser):
        parser.add_argument(
            '-a', '--all',
            action='store_true',
            help='Include disabled plugins'
        )
        parser.add_argument(
            '-j', '--json',
            action='store_true',
            help='JSON output format'
        )
        parser.add_argument(
            '--installed',
            action='store_true',
            help='Show only installed plugins'
        )
        parser.add_argument(
            '--upgradable',
            action='store_true',
            help='Show only upgradable plugins'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        self.verbose = getattr(args, 'verbose', 0)
        
        # Find all plugin.json files
        plugins = []
        for root, dirs, files in os.walk('plugins'):
            if 'plugin.json' in files:
                with open(os.path.join(root, 'plugin.json'), 'r') as f:
                    try:
                        data = json.load(f)
                        data['path'] = root
                        plugins.append(data)
                    except:
                        pass
        
        if args.json:
            print(json.dumps(plugins, indent=2))
        else:
            print(f"\n📦 Found {len(plugins)} plugin(s)\n")
            
            for p in plugins:
                status = "✓" if p.get('is_builtin') else "○"
                name = p.get('name', 'Unknown')
                version = p.get('version', '?')
                category = p.get('category', '?')
                
                print(f"   {status} {name:<30} v{version:<10} [{category}]")
        
        return 0