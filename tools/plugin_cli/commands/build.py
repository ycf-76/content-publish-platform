"""Build Command - Build production package."""

import argparse
import os
import shutil
from datetime import datetime
from .base import BaseCommand


class BuildCommand(BaseCommand):
    """Build production package."""
    
    name = "build"
    help = "Build production package"
    
    def add_arguments(self, parser: argparse.ArgumentParser):
        parser.add_argument(
            '-o', '--output',
            type=str,
            default='./dist',
            help='Output directory (default: ./dist)'
        )
        parser.add_argument(
            '--format',
            type=str,
            choices=['zip', 'tar.gz', 'wheel'],
            default='zip',
            help='Package format (default: zip)'
        )
        parser.add_argument(
            '--minify',
            action='store_true',
            help='Minify code'
        )
        parser.add_argument(
            '--no-check',
            action='store_true',
            help='Skip pre-build checks'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        self.verbose = getattr(args, 'verbose', 0)
        
        print(f"\n📦 Building plugin for production...")
        
        # Check for plugin.json
        if not os.path.exists('plugin.json'):
            self.print_error("plugin.json not found. Are you in the plugin root?")
            return 1
        
        # Create output dir
        output_dir = args.output
        os.makedirs(output_dir, exist_ok=True)
        
        # Get plugin info
        # TODO: Read from plugin.json
        plugin_name = "my-plugin"
        version = "0.1.0"
        
        package_name = f"{plugin_name}-v{version}"
        
        if args.format == 'zip':
            output_file = os.path.join(output_dir, f"{package_name}.zip")
            self._create_zip(output_file)
        elif args.format == 'tar.gz':
            output_file = os.path.join(output_dir, f"{package_name}.tar.gz")
            self._create_tar_gz(output_file)
        elif args.format == 'wheel':
            output_file = os.path.join(output_dir, f"{package_name}-py3-none-any.whl")
            self._create_wheel(output_file)
        
        file_size = os.path.getsize(output_file) / 1024
        
        print(f"\n✅ Build complete!")
        print(f"   Output: {output_file}")
        print(f"   Size: {file_size:.1f} KB\n")
        
        return 0
    
    def _create_zip(self, output_file):
        """Create ZIP archive."""
        import zipfile
        with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk('.'):
                if '__pycache__' in root or '.git' in root:
                    continue
                for file in files:
                    if file.endswith('.pyc'):
                        continue
                    filepath = os.path.join(root, file)
                    arcname = os.path.relpath(filepath, '.')
                    zipf.write(filepath, arcname)
    
    def _create_tar_gz(self, output_file):
        """Create tar.gz archive."""
        import tarfile
        with tarfile.open(output_file, 'w:gz') as tar:
            for root, dirs, files in os.walk('.'):
                if '__pycache__' in root or '.git' in root:
                    continue
                for file in files:
                    if file.endswith('.pyc'):
                        continue
                    filepath = os.path.join(root, file)
                    arcname = os.path.relpath(filepath, '.')
                    tar.add(filepath, arcname=arcname)
    
    def _create_wheel(self, output_file):
        """Create wheel package (placeholder)."""
        self.print_info("Wheel creation not yet implemented, using zip instead")
        self._create_zip(output_file.replace('.whl', '.zip'))