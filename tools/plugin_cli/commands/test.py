"""Test Command - Run tests."""

import argparse
import subprocess
import sys
from .base import BaseCommand


class TestCommand(BaseCommand):
    """Run plugin tests."""
    
    name = "test"
    help = "Run tests with coverage"
    
    def add_arguments(self, parser: argparse.ArgumentParser):
        parser.add_argument(
            '-c', '--coverage',
            action='store_true',
            help='Generate coverage report'
        )
        parser.add_argument(
            '-v', '--verbose',
            action='store_true',
            help='Verbose output'
        )
        parser.add_argument(
            '--failfast',
            action='store_true',
            help='Stop on first failure'
        )
        parser.add_argument(
            '-k',
            type=str,
            default=None,
            help='Only run tests matching pattern'
        )
        parser.add_argument(
            '--parallel',
            action='store_true',
            help='Run tests in parallel'
        )
        parser.add_argument(
            '--reporter',
            type=str,
            choices=['text', 'json', 'html', 'xml'],
            default='text',
            help='Report format (default: text)'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        self.verbose = getattr(args, 'verbose', 0)
        
        cmd = [sys.executable, '-m', 'pytest']
        
        if args.coverage:
            cmd.extend(['--cov=.', '--cov-report=term-missing'])
            if args.reporter == 'html':
                cmd.append('--cov-report=html')
        
        if args.verbose:
            cmd.append('-v')
        
        if args.failfast:
            cmd.append('--exitfirst')
        
        if args.k:
            cmd.extend(['-k', args.k])
        
        if args.parallel:
            cmd.extend(['-n', 'auto'])
        
        print(f"\n🧪 Running tests...")
        print(f"   Command: {' '.join(cmd)}\n")
        
        try:
            result = subprocess.run(cmd)
            return result.returncode
        except Exception as e:
            self.print_error(f"Failed to run tests: {e}")
            return 1