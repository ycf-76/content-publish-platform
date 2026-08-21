"""Doctor Command - Diagnose common issues."""

import argparse
import sys
import os
import json
from .base import BaseCommand


class DoctorCommand(BaseCommand):
    """Diagnose common plugin development issues."""
    
    name = "doctor"
    help = "Diagnose common issues"
    aliases = ['diag', 'check']
    
    def add_arguments(self, parser: argparse.ArgumentParser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Auto-fix found issues'
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show detailed diagnostic info'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        self.verbose = getattr(args, 'verbose', 0)
        
        print("\n🔍 Running diagnostics...\n")
        
        checks = [
            self._check_python_version,
            self._check_plugin_json,
            self._check_entry_point,
            self._check_requirements,
            self._check_git,
            self._check_tests,
        ]
        
        passed = 0
        warnings = 0
        errors = 0
        
        for check in checks:
            try:
                result = check()
                if result == 'OK':
                    passed += 1
                    self.print_success(f"Check {check.__name__}")
                elif result == 'WARN':
                    warnings += 1
                    self.print_warning(f"Check {check.__name__} has warnings")
                else:
                    errors += 1
                    self.print_error(f"Check {check.__name__} failed")
            except Exception as e:
                errors += 1
                if args.verbose:
                    import traceback
                    traceback.print_exc()
        
        # Summary
        print(f"\n{'='*60}")
        print(f"📊 Summary:")
        print(f"   ✅ Passed: {passed}")
        print(f"   ⚠️  Warnings: {warnings}")
        print(f"   ❌ Errors: {errors}\n")
        
        if errors > 0:
            return 1
        return 0
    
    def _check_python_version(self):
        """Check Python version."""
        version = sys.version_info
        if version >= (3, 10):
            return 'OK'
        return 'ERROR'
    
    def _check_plugin_json(self):
        """Check plugin.json exists and is valid."""
        if not os.path.exists('plugin.json'):
            return 'ERROR'
        
        try:
            with open('plugin.json', 'r') as f:
                data = json.load(f)
            
            required = ['id', 'version', 'name', 'category']
            for field in required:
                if field not in data:
                    return 'WARN'
            
            return 'OK'
        except json.JSONDecodeError:
            return 'ERROR'
    
    def _check_entry_point(self):
        """Check entry point file exists."""
        # TODO: Read from plugin.json and verify
        return 'WARN'  # Not yet implemented
    
    def _check_requirements(self):
        """Check requirements.txt."""
        if os.path.exists('requirements.txt'):
            return 'OK'
        return 'WARN'
    
    def _check_git(self):
        """Check git initialization."""
        if os.path.exists('.git'):
            return 'OK'
        return 'WARN'
    
    def _check_tests(self):
        """Check for test files."""
        if os.path.exists('tests') and any(
            f.endswith('.py') for f in os.listdir('tests')
        ):
            return 'OK'
        return 'WARN'