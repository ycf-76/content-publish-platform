"""
Plugin Developer CLI Toolkit
============================

A comprehensive command-line tool for plugin development,
testing, debugging, and publishing.

Usage:
    plugin <command> [options]

Commands:
    create      Create a new plugin from template
    dev         Start development server with hot reload
    test        Run tests with coverage
    build       Build production package
    publish     Publish to marketplace
    list        List local plugins
    info        Show plugin details
    config      Manage plugin configuration
    logs        View plugin logs
    doctor      Diagnose common issues
    version     Manage version numbers
    help        Show this help message

Examples:
    plugin create my-awesome-plugin --type workflow_node
    plugin dev -p 9000 --debug
    plugin test -c --parallel
    plugin build --format wheel
    plugin publish --changelog CHANGELOG.md

For detailed help: plugin <command> --help
"""

__version__ = "1.0.0"
__author__ = "Platform Team"
__email__ = "dev@your-platform.com"

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))