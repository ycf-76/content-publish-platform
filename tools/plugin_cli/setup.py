"""Setup configuration for plugin-cli."""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists else ""

# Read version from __init__.py
version = "1.0.0"
init_path = Path(__file__).parent / "__init__.py"
if init_path.exists():
    content = init_path.read_text()
    import re
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if match:
        version = match.group(1)

setup(
    name="plugin-dev-toolkit",
    version=version,
    author="Platform Team",
    author_email="dev@your-platform.com",
    description="Plugin Developer CLI Toolkit - Develop, test, debug and publish plugins",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/your-org/plugin-dev-toolkit",
    
    packages=find_packages(),
    
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Operating System :: OS Independent",
    ],
    
    python_requires=">=3.10",
    
    install_requires=[
        "click>=8.0.0",          # CLI framework (optional, can use argparse)
        "rich>=13.0.0",           # Terminal formatting
        "httpx>=0.24.0",          # HTTP client
        "watchfiles>=0.20.0",     # File watching for hot reload
        "jinja2>=3.1.0",          # Template rendering
        "jsonschema>=4.17.0",     # Schema validation
        "pydantic>=2.0.0",        # Data validation
    ],
    
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.0.0",
            "mypy>=1.0.0",
            "ruff>=0.1.0",
            "black>=23.0.0",
        ],
        "docs": [
            "mkdocs>=1.5.0",
            "mkdocs-material>=9.0.0",
        ],
    },
    
    entry_points={
        "console_scripts": [
            "plugin=plugin_cli.cli:main",
        ],
    },
    
    include_package_data=True,
    
    project_urls={
        "Bug Tracker": "https://github.com/your-org/plugin-dev-toolkit/issues",
        "Documentation": "https://docs.your-platform.com/plugins/cli",
        "Source Code": "https://github.com/your-org/plugin-dev-toolkit",
    },
)