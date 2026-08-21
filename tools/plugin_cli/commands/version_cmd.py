"""Version Command - Manage version numbers."""

import argparse
import json
import re
from .base import BaseCommand


class VersionCommand(BaseCommand):
    """Manage plugin version."""
    
    name = "version"
    help = "Manage version numbers"
    aliases = ['ver']
    
    def add_arguments(self, parser: argparse.ArgumentParser):
        parser.add_argument(
            'action',
            type=str,
            nargs='?',
            choices=['patch', 'minor', 'major', 'prerelease'],
            help='Version bump action'
        )
        parser.add_argument(
            '--pre',
            type=str,
            choices=['alpha', 'beta', 'rc'],
            help='Prerelease tag'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        self.verbose = getattr(args, 'verbose', 0)
        
        if not args.action:
            # Show current version
            return self._show_version()
        
        # Bump version
        return self._bump_version(args.action, args.pre)
    
    def _show_version(self):
        """Display current version."""
        
        # Read from plugin.json
        try:
            with open('plugin.json', 'r') as f:
                data = json.load(f)
            
            version = data.get('version', 'unknown')
            print(f"\n📌 Current version: {version}\n")
            return 0
            
        except FileNotFoundError:
            self.print_error("plugin.json not found")
            return 1
    
    def _bump_version(self, action: str, pre: str = None) -> int:
        """Bump version number."""
        
        try:
            with open('plugin.json', 'r+') as f:
                data = json.load(f)
                
                current = data.get('version', '0.0.1')
                
                # Parse version
                match = re.match(r'(\d+)\.(\d+)\.(\d+)(?:-(.+))?', current)
                if not match:
                    self.print_error(f"Invalid version format: {current}")
                    return 1
                
                major, minor, patch = int(match[1]), int(match[2]), int(match[3])
                prerelease = match[4] or None
                
                # Bump according to action
                if action == 'major':
                    major += 1
                    minor = 0
                    patch = 0
                    prerelease = None
                elif action == 'minor':
                    minor += 1
                    patch = 0
                    prerelease = None
                elif action == 'patch':
                    patch += 1
                    prerelease = None
                elif action == 'prerelease':
                    if not pre:
                        pre = prerelease.split('.')[0] if prerelease else 'alpha'
                    
                    if prerelease and pre in prerelease:
                        # Increment prerelease number
                        parts = prerelease.split('.')
                        num = int(parts[1]) + 1 if len(parts) > 1 else 1
                        prerelease = f"{parts[0]}.{num}"
                    else:
                        prerelease = f"{pre}.1"
                
                # Build new version
                new_version = f"{major}.{minor}.{patch}"
                if prerelease:
                    new_version = f"{new_version}-{prerelease}"
                
                # Update file
                f.seek(0)
                data['version'] = new_version
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.truncate()
                
                print(f"\n📌 Version bumped: {current} → {new_version}\n")
                return 0
                
        except Exception as e:
            self.print_error(f"Failed to update version: {e}")
            return 1