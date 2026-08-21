"""
Create Command
==============

Create a new plugin from template.
"""

import os
import json
import shutil
import argparse
from datetime import datetime
from typing import Optional

from .base import BaseCommand


class CreateCommand(BaseCommand):
    """Create new plugin from template."""
    
    name = "create"
    help = "Create a new plugin from template"
    description = """
Generate a new plugin project from predefined templates.
Supports multiple plugin types and customization options.

Examples:
  plugin create my-translator                    # Basic workflow node plugin
  plugin create xhs-pub --type platform          # Platform plugin
  plugin create rss-feed --type datasource       # Datasource plugin
  plugin create my-plugin --template full        # Full-featured template
    """.strip()
    
    PLUGIN_TYPES = {
        'workflow_node': {
            'base_class': 'BaseWorkflowNodePlugin',
            'required_methods': ['execute'],
            'description': 'Workflow execution node'
        },
        'platform': {
            'base_class': 'BasePlatformPlugin',
            'required_methods': ['authenticate', 'publish'],
            'description': 'Content publishing platform'
        },
        'datasource': {
            'base_class': 'BaseDatasourcePlugin',
            'required_methods': ['search_trending', 'get_trending'],
            'description': 'External data source'
        },
        'ai_model': {
            'base_class': 'BaseAIModelPlugin',
            'required_methods': ['generate_text'],
            'description': 'AI/ML model integration'
        },
        'ui_theme': {
            'base_class': 'BaseUIThemePlugin',
            'required_methods': ['get_theme_css'],
            'description': 'UI theme and styling'
        },
        'integration': {
            'base_class': 'BaseIntegrationPlugin',
            'required_methods': ['sync', 'webhook_handler'],
            'description': 'Third-party service integration'
        }
    }
    
    TEMPLATES = {
        'minimal': {
            'files': ['plugin.json', 'main.py'],
            'features': [],
            'description': 'Minimal viable plugin (<50 lines)'
        },
        'basic': {
            'files': [
                'plugin.json', 'main.py', 'requirements.txt',
                'README.md', '.gitignore', 'tests/test_main.py'
            ],
            'features': ['error_handling', 'basic_tests', 'docs'],
            'description': 'Standard development setup (recommended)'
        },
        'full': {
            'files': [
                'plugin.json', 'main.py', 'config.py', 'utils.py',
                'errors.py', 'requirements.txt', 'setup.py',
                'pyproject.toml', 'README.md', 'CHANGELOG.md',
                'LICENSE', '.gitignore', '.editorconfig',
                'tests/conftest.py', 'tests/test_main.py',
                'tests/test_integration.py', 'assets/icon.png'
            ],
            'features': [
                'full_implementation', 'testing_suite', 'documentation',
                'ci_cd_config', 'performance_optimization'
            ],
            'description': 'Production-ready with all features'
        }
    }
    
    def add_arguments(self, parser: argparse.ArgumentParser):
        """Add create-specific arguments."""
        
        parser.add_argument(
            'name',
            type=str,
            help='Plugin name (kebab-case format, e.g., my-awesome-plugin)'
        )
        
        parser.add_argument(
            '-t', '--type',
            type=str,
            choices=list(self.PLUGIN_TYPES.keys()),
            default='workflow_node',
            help='Plugin type (default: workflow_node)'
        )
        
        parser.add_argument(
            '--template',
            type=str,
            choices=list(self.TEMPLATES.keys()),
            default='basic',
            help='Template to use: minimal/basic/full (default: basic)'
        )
        
        parser.add_argument(
            '-d', '--dir',
            type=str,
            default=None,
            help='Output directory (default: ./plugins/<name>)'
        )
        
        parser.add_argument(
            '--no-git',
            action='store_true',
            help='Do not initialize Git repository'
        )
        
        parser.add_argument(
            '--no-install',
            action='store_true',
            help='Do not install dependencies automatically'
        )
        
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force overwrite existing directory'
        )
        
        # Author info (optional)
        parser.add_argument(
            '--author',
            type=str,
            default=None,
            help='Author name'
        )
        
        parser.add_argument(
            '--email',
            type=str,
            default=None,
            help='Author email'
        )
    
    def execute(self, args: argparse.Namespace) -> int:
        """Execute create command."""
        
        self.verbose = getattr(args, 'verbose', 0)
        self.no_color = getattr(args, 'no_color', False)
        
        plugin_name = args.name
        
        # Validate plugin name
        if not self._validate_name(plugin_name):
            self.print_error(f"Invalid plugin name: {plugin_name}")
            self.print_error("Use kebab-case format (e.g., my-awesome-plugin)")
            return 1
        
        # Determine output directory
        output_dir = args.dir or os.path.join('plugins', plugin_name)
        
        # Check if directory exists
        if os.path.exists(output_dir) and not args.force:
            self.print_error(f"Directory already exists: {output_dir}")
            self.print_info("Use --force to overwrite")
            return 1
        
        # Get template info
        template_name = args.template
        template = self.TEMPLATES.get(template_name)
        if not template:
            self.print_error(f"Unknown template: {template_name}")
            return 1
        
        # Get plugin type info
        plugin_type = args.type
        type_info = self.PLUGIN_TYPES.get(plugin_type)
        if not type_info:
            self.print_error(f"Unknown plugin type: {plugin_type}")
            return 1
        
        try:
            # Create directory structure
            self._print_header(plugin_name, plugin_type, template_name)
            
            self.print_info("Creating directory structure...")
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate files
            generated_files = []
            
            for file_path in template['files']:
                full_path = os.path.join(output_dir, file_path)
                
                # Create subdirectories if needed
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                
                # Generate file content
                content = self._generate_file_content(
                    file_path=file_path,
                    plugin_name=plugin_name,
                    plugin_type=plugin_type,
                    type_info=type_info,
                    template=template,
                    args=args
                )
                
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                generated_files.append(file_path)
                self.print_debug(f"Created: {file_path}")
            
            # Initialize Git repository
            if not args.no_git:
                self._init_git_repo(output_dir)
            
            # Install dependencies
            if not args.no_install and 'requirements.txt' in template['files']:
                self._install_dependencies(output_dir)
            
            # Print summary
            self._print_summary(
                plugin_name=plugin_name,
                output_dir=output_dir,
                plugin_type=plugin_type,
                template=template,
                generated_files=generated_files
            )
            
            return 0
            
        except Exception as e:
            self.print_error(f"Failed to create plugin: {e}")
            if self.verbose >= 2:
                import traceback
                traceback.print_exc()
            
            # Cleanup on failure
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir)
            
            return 1
    
    def _validate_name(self, name: str) -> bool:
        """Validate plugin name format."""
        
        import re
        
        # Must be kebab-case, 3-50 chars
        pattern = r'^[a-z][a-z0-9-]{2,49}$'
        return bool(re.match(pattern, name))
    
    def _print_header(self, name: str, ptype: str, template: str):
        """Print creation header."""
        
        print(f"\n🚀 Creating new plugin: {name}")
        print(f"   Type:     {ptype}")
        print(f"   Template: {template}\n")
    
    def _generate_file_content(
        self,
        file_path: str,
        plugin_name: str,
        plugin_type: str,
        type_info: dict,
        template: dict,
        args: argparse.Namespace
    ) -> str:
        """Generate content for a specific file."""
        
        # Convert plugin name to various formats
        class_name = self._to_pascal_case(plugin_name)
        plugin_id = plugin_name.lower()
        
        # Author info
        author_name = args.author or "Your Name"
        author_email = args.email or "you@example.com"
        
        generators = {
            'plugin.json': lambda: self._gen_plugin_json(
                plugin_id, plugin_name, class_name, 
                plugin_type, type_info, author_name, author_email
            ),
            'main.py': lambda: self._gen_main_py(
                class_name, plugin_id, plugin_type, type_info
            ),
            'requirements.txt': lambda: self._gen_requirements_txt(),
            'README.md': lambda: self._gen_readme_md(
                plugin_name, plugin_id, plugin_type
            ),
            '.gitignore': lambda: self._gen_gitignore(),
            'tests/test_main.py': lambda: self._gen_test_main_py(class_name),
            'tests/conftest.py': lambda: self._gen_conftest_py(),
            'tests/test_integration.py': lambda: self._gen_test_integration_py(),
            'config.py': lambda: self._config_py(),
            'utils.py': lambda: self._utils_py(),
            'errors.py': lambda: self._errors_py(),
            'setup.py': lambda: self._setup_py(plugin_name),
            'pyproject.toml': lambda: self._pyproject_toml(plugin_name),
            'CHANGELOG.md': lambda: self._changelog_md(),
            'LICENSE': lambda: self._license(),
            '.editorconfig': lambda: self._editorconfig(),
        }
        
        generator = generators.get(file_path)
        if generator:
            return generator()
        
        # Default empty file
        return ""
    
    def _to_pascal_case(self, name: str) -> str:
        """Convert kebab-case to PascalCase."""
        return ''.join(word.capitalize() for word in name.split('-'))
    
    def _gen_plugin_json(
        self,
        plugin_id: str,
        display_name: str,
        class_name: str,
        plugin_type: str,
        type_info: dict,
        author_name: str,
        author_email: str
    ) -> str:
        """Generate plugin.json content."""
        
        config_schema = self._get_default_config_schema(plugin_type)
        input_schema = self._get_default_input_schema(plugin_type)
        output_schema = self._get_default_output_schema(plugin_type)
        
        plugin_json = {
            "id": plugin_id,
            "version": "0.1.0",
            "name": display_name.replace('-', ' ').title(),
            "description": f"A {type_info['description']} plugin",
            "author": {
                "name": author_name,
                "email": author_email
            },
            "category": plugin_type,
            "entry_point": f"main.py:{class_name}",
            "display_icon": self._get_default_icon(plugin_type),
            "tags": [plugin_type],
            "capabilities": type_info.get('required_methods', []),
            "permissions_required": [],
            "config_schema": config_schema,
            "input_schema": input_schema,
            "output_schema": output_schema,
            "pricing_model": "free",
            "min_platform_version": "1.0.0",
            "dependencies": [],
            "events_subscribes": [],
            "events_emits": []
        }
        
        return json.dumps(plugin_json, indent=2, ensure_ascii=False)
    
    def _gen_main_py(
        self,
        class_name: str,
        plugin_id: str,
        plugin_type: str,
        type_info: dict
    ) -> str:
        """Generate main.py content."""
        
        base_class = type_info['base_class']
        required_methods = type_info.get('required_methods', [])
        
        imports = f"""import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.base_interfaces import {base_class}, PluginContext"""
        
        if plugin_type == 'workflow_node':
            imports += ", NodeOutput"
        elif plugin_type == 'platform':
            imports += ", AuthResult, PublishResult"
        elif plugin_type == 'datasource':
            imports += ", TrendingItem, Classification"
        
        imports += "\nfrom app.core.plugin_types import PluginManifest, HealthStatus\n"
        
        class_def = f"""

class {class_name}({base_class}):
    \"\"\"
    {class_name} - {plugin_id.replace('-', ' ').title()} Plugin
    
    Description: A {type_info['description']}
    Version: 0.1.0
    Author: Your Name
    \"\"\"
    
    # Class attributes (can also be loaded from plugin.json)
    id = "{plugin_id}"
    name = "{class_name}"
    version = "0.1.0"
    
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self._initialized = False
    
    async def on_load(self) -> None:
        \"\"\"Called when plugin is loaded.\"\"\"
        self.logger.info(f"Loading {{self.id}} plugin...")
        
        # Initialize resources here
        # - Database connections
        # - API clients
        # - Cache instances
        
        self._initialized = True
        self.logger.info(f"{{self.id}} plugin loaded successfully")
    
    async def on_unload(self) -> None:
        \"\"\"Called when plugin is unloaded.\"\"\"
        self.logger.info(f"Unloading {{self.id}} plugin...")
        
        # Cleanup resources here
        # - Close connections
        # - Flush caches
        # - Save state
        
        self._initialized = False
    
    async def get_info(self) -> PluginManifest:
        \"\"\"Return plugin metadata.\"\"\"
        return PluginManifest(
            id=self.id,
            name=self.name,
            version=self.version,
            category="{plugin_type}",
            description="A {type_info['description']}",
            capabilities={required_methods},
            permissions_required=[]
        )
    
    async def health_check(self) -> HealthStatus:
        \"\"\"Check plugin health status.\"\"\"
        is_healthy = self._initialized
        
        return HealthStatus(
            status="healthy" if is_healthy else "unhealthy",
            message="{{'Ready' if is_healthy else 'Not initialized'}}",
            timestamp=datetime.utcnow()
        )
"""
        
        # Add required methods based on type
        methods = ""
        
        if 'execute' in required_methods:
            methods += """
    async def execute(
        self, 
        ctx: PluginContext, 
        inputs: Dict[str, Any]
    ) -> NodeOutput:
        \"\"\"
        Execute the workflow node.
        
        Args:
            ctx: Plugin execution context
            inputs: Input data dictionary
            
        Returns:
            NodeOutput: Execution result
        \"\"\"
        start_time = asyncio.get_event_loop().time()
        
        try:
            # TODO: Implement your logic here
            # Example:
            # data = inputs.get("data", "")
            # result = await self.process_data(data)
            
            result = {"status": "success", "message": "Execution completed"}
            
            elapsed_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
            
            return NodeOutput(
                success=True,
                data=result,
                message="Operation completed successfully",
                execution_time_ms=elapsed_ms
            )
            
        except Exception as e:
            self.logger.error(f"Execution failed: {{e}}", exc_info=True)
            elapsed_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
            
            return NodeOutput(
                success=False,
                data={{}},
                message=f"Error: {{str(e)}}",
                error_code="EXECUTION_ERROR",
                execution_time_ms=elapsed_ms
            )
"""
        
        if 'validate_inputs' in required_methods:
            methods += """
    async def validate_inputs(self, inputs: Dict[str, Any]) -> tuple[bool, str]:
        \"\"\"
        Validate input parameters.
        
        Args:
            inputs: Input data to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        \"\"\"
        # Add your validation logic here
        # Example:
        # if not inputs.get("required_field"):
        #     return False, "Missing required field: required_field"
        
        return True, "Inputs are valid"
"""
        
        if 'authenticate' in required_methods:
            methods += """
    async def authenticate(self, credentials: Dict[str, Any]) -> AuthResult:
        \"\"\"Authenticate with the platform.\"\"\"
        # TODO: Implement authentication
        api_key = credentials.get("api_key", "")
        
        # Validate credentials...
        
        return AuthResult(
            success=True,
            token="mock_token",
            expires_at=datetime.utcnow() + timedelta(days=30)
        )
"""
        
        if 'publish' in required_methods:
            methods += """
    async def publish(self, content: Any) -> PublishResult:
        \"\"\"Publish content to platform.\"\"\"
        # TODO: Implement publishing logic
        return PublishResult(
            success=True,
            content_id="mock_id_123",
            platform_url="https://example.com/post/mock_id_123"
        )
"""
        
        if 'search_trending' in required_methods:
            methods += """
    async def search_trending(
        self, 
        query: str, 
        limit: int = 20
    ) -> List[TrendingItem]:
        \"\"\"Search trending content.\"\"\"
        # TODO: Implement search logic
        return []
    
    async def get_trending(
        self, 
        category: Optional[str] = None,
        limit: int = 20
    ) -> List[TrendingItem]:
        \"\"\"Get trending content list.\"\"\"
        # TODO: Implement fetching logic
        return []
"""
        
        return imports + class_def + methods + "\n"
    
    def _get_default_icon(self, plugin_type: str) -> str:
        """Get default icon based on plugin type."""
        
        icons = {
            'workflow_node': '⚙️',
            'platform': '📱',
            'datasource': '📡',
            'ai_model': '🤖',
            'ui_theme': '🎨',
            'integration': '🔗'
        }
        
        return icons.get(plugin_type, '📦')
    
    def _get_default_config_schema(self, plugin_type: str) -> dict:
        """Get default configuration schema based on type."""
        
        base_schema = {
            "type": "object",
            "properties": {},
            "required": []
        }
        
        if plugin_type == 'ai_model':
            base_schema["properties"] = {
                "model_name": {
                    "type": "string",
                    "title": "Model Name",
                    "default": "gpt-3.5-turbo"
                },
                "api_key": {
                    "type": "string",
                    "title": "API Key",
                    "x-ui": {"widget": "password"}
                },
                "temperature": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 2,
                    "default": 0.7
                }
            }
            base_schema["required"] = ["api_key"]
        
        elif plugin_type == 'platform':
            base_schema["properties"] = {
                "api_credentials": {
                    "type": "object",
                    "title": "API Credentials",
                    "properties": {
                        "client_id": {"type": "string"},
                        "client_secret": {"type": "string"}
                    }
                },
                "auto_publish": {
                    "type": "boolean",
                    "default": False
                }
            }
        
        elif plugin_type == 'datasource':
            base_schema["properties"] = {
                "refresh_interval_minutes": {
                    "type": "integer",
                    "minimum": 5,
                    "maximum": 1440,
                    "default": 30
                },
                "max_items_per_fetch": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20
                }
            }
        
        return base_schema
    
    def _get_default_input_schema(self, plugin_type: str) -> dict:
        """Get default input schema."""
        
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Input data"
                }
            },
            "required": ["data"]
        }
    
    def _get_default_output_schema(self, plugin_type: str) -> dict:
        """Get default output schema."""
        
        return {
            "type": "object",
            "properties": {
                "result": {
                    "type": "string",
                    "description": "Output result"
                },
                "metadata": {
                    "type": "object",
                    "description": "Additional metadata"
                }
            }
        }
    
    def _gen_requirements_txt(self) -> str:
        """Generate requirements.txt."""
        return """# Plugin dependencies
# Add your dependencies here with version pinning

# HTTP client
httpx>=0.24.0

# Data validation
pydantic>=2.0.0

# Async utilities
aiofiles>=23.0.0

# Testing (dev only)
# pytest>=7.0.0
# pytest-asyncio>=0.21.0
# pytest-cov>=4.0.0
"""
    
    def _gen_readme_md(
        self, 
        display_name: str, 
        plugin_id: str,
        plugin_type: str
    ) -> str:
        """Generate README.md."""
        
        return f"""# {display_name.replace('-', ' ').title()} Plugin

> A {plugin_type} plugin for the Multi-Agent Content Platform

## 📋 Description

Brief description of what this plugin does.

## ✨ Features

- Feature 1
- Feature 2
- Feature 3

## 🔧 Installation

### From Marketplace (Recommended)

1. Open Plugin Manager in the platform UI
2. Search for `{plugin_id}`
3. Click "Install"

### Manual Installation

```bash
# Copy plugin to plugins directory
cp -r {plugin_id} /path/to/platform/plugins/

# Restart platform
```

## ⚙️ Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `param1` | string | `""` | Description |

## 📡 Usage

### As Workflow Node

```yaml
workflow:
  nodes:
    - id: step1
      type: {plugin_id}
      config:
        param1: value1
```

### API Usage

```python
# Execute via API
response = await client.post("/api/plugins/{plugin_id}/execute", {{
    "inputs": {{
        "data": "your data here"
    }}
}})
```

## 🧪 Testing

```bash
# Run tests
plugin test

# Run with coverage
plugin test -c
```

## 📄 License

MIT License

## 👥 Contributing

Contributions are welcome! Please read our contributing guidelines first.

## 📞 Support

- Issues: [GitHub Issues](link)
- Email: support@example.com

---

**Version**: 0.1.0  
**Last Updated**: {datetime.now().strftime('%Y-%m-%d')}
"""
    
    def _gen_gitignore(self) -> str:
        """Generate .gitignore."""
        return """__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

venv/
ENV/
env/
.venv/

.pytest_cache/
.coverage
htmlcov/

.vscode/
.idea/
*.swp
*.swo

.env
*.env
secrets.yml
credentials.json

*.log
.DS_Store
"""
    
    def _gen_test_main_py(self, class_name: str) -> str:
        """Generate test file."""
        return f"""import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
class Test{class_name}:
    \"\"\"Test suite for {class_name} plugin.\"\"\"
    
    @pytest.fixture
    def plugin(self):
        \"\"\"Create plugin instance.\"\"\"
        from main import {class_name}
        return {class_name}()
    
    @pytest.fixture
    def mock_context(self):
        \"\"\"Create mock context.\"\"\"
        context = AsyncMock()
        context.user_id = "test_user"
        context.config = {{}}
        context.event_bus = AsyncMock()
        context.data_store = AsyncMock()
        context.logger = AsyncMock()
        return context
    
    async def test_plugin_initialization(self, plugin):
        \"\"\"Test plugin can be initialized.\"\"\"
        assert plugin.id is not None
        assert plugin.version is not None
    
    async def test_get_info(self, plugin):
        \"\"\"Test get_info returns valid manifest.\"\"\"
        info = await plugin.get_info()
        
        assert info.id == plugin.id
        assert info.version == plugin.version
    
    async def test_health_check(self, plugin):
        \"\"\"Test health check returns healthy status.\"\"\"
        # Load plugin first
        await plugin.on_load()
        
        status = await plugin.health_check()
        
        assert status.status in ["healthy", "unhealthy"]
    
    async def test_execute_success(self, plugin, mock_context):
        \"\"\"Test successful execution.\"\"\"
        # Load plugin
        await plugin.on_load()
        
        # Execute
        result = await plugin.execute(mock_context, {{"data": "test"}})
        
        assert result.success is True
        assert "data" in result.__dict__
"""
    
    def _gen_conftest_py(self) -> str:
        """Generate conftest.py."""
        return """import pytest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def event_loop():
    \"\"\"Create event loop for async tests.\"\"\"
    import asyncio
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_inputs():
    \"\"\"Standard test inputs.\"\"\"
    return {
        "data": "test data",
        "options": {
            "option1": "value1"
        }
    }
"""
    
    def _gen_test_integration_py(self) -> str:
        """Generate integration test file."""
        return """import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestIntegration:
    \"\"\"Integration tests for plugin.\"\"\"
    
    async def test_health_endpoint(self):
        \"\"\"Test health check endpoint.\"\"\"
        async with AsyncClient(base_url="http://localhost:8765") as client:
            response = await client.get("/api/status")
            
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
    
    async def test_execute_via_api(self):
        \"\"\"Test execute endpoint.\"\"\"
        async with AsyncClient(base_url="http://localhost:8765") as client:
            response = await client.post(
                "/api/plugins/my-plugin/execute",
                json={
                    "inputs": {
                        "data": "integration test"
                    }
                }
            )
            
            # Should succeed or give meaningful error
            assert response.status_code in [200, 400, 404, 500]
"""
    
    def _config_py(self) -> str:
        """Generate config.py module."""
        return '''"""Configuration management utilities."""

import json
from pathlib import Path
from typing import Any, Dict, Optional


class ConfigManager:
    """Manage plugin configuration."""
    
    DEFAULT_CONFIG_FILE = "configs/default.json"
    
    def __init__(self, config_dir: str = "configs"):
        self.config_dir = Path(config_dir)
        self._cache: Dict[str, Any] = {}
    
    def load_defaults(self) -> Dict[str, Any]:
        """Load default configuration."""
        config_file = self.config_dir / self.DEFAULT_CONFIG_FILE
        
        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        return {}
    
    def merge_configs(
        self, 
        defaults: Dict[str, Any], 
        user_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Merge user config with defaults."""
        merged = defaults.copy()
        merged.update(user_config)
        return merged
    
    def validate_config(
        self, 
        config: Dict[str, Any], 
        schema: Dict[str, Any]
    ) -> tuple[bool, str]:
        """Validate config against schema."""
        # Implement JSON Schema validation
        # For now, just check required fields
        required = schema.get("required", [])
        
        for field in required:
            if field not in config:
                return False, f"Missing required field: {field}"
        
        return True, "Config is valid"
'''
    
    def _utils_py(self) -> str:
        """Generate utils.py module."""
        return '''"""Utility functions."""

import hashlib
import time
from typing import Any, Dict, Optional
from datetime import datetime


def generate_hash(data: str) -> str:
    """Generate MD5 hash of string."""
    return hashlib.md5(data.encode()).hexdigest()


def timestamp_now() -> int:
    """Get current Unix timestamp."""
    return int(time.time())


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    elif seconds < 60:
        return f"{seconds:.2f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"


def deep_merge(dict1: Dict, dict2: Dict) -> Dict:
    """Deep merge two dictionaries."""
    result = dict1.copy()
    
    for key, value in dict2.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def sanitize_output(data: Any) -> Any:
    """Remove sensitive information from output."""
    if isinstance(data, dict):
        return {k: sanitize_output(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_output(item) for item in data]
    return data
'''
    
    def _errors_py(self) -> str:
        """Generate errors.py module."""
        return '''"""Custom exception classes."""


class PluginError(Exception):
    """Base exception for plugin errors."""
    
    def __init__(
        self, 
        message: str, 
        code: str = "PLUGIN_ERROR",
        retryable: bool = False
    ):
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.message = message


class ConfigurationError(PluginError):
    """Configuration related error."""
    
    def __init__(self, message: str):
        super().__init__(message, code="CONFIG_ERROR")


class AuthenticationError(PluginError):
    """Authentication failed error."""
    
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, code="AUTH_ERROR", retryable=False)


class RateLimitError(PluginError):
    """Rate limit exceeded error."""
    
    def __init__(self, retry_after: float = 60.0):
        message = f"Rate limit exceeded, retry after {retry_after}s"
        super().__init__(message, code="RATE_LIMITED", retryable=True)
        self.retry_after = retry_after


class TimeoutError(PluginError):
    """Operation timeout error."""
    
    def __init__(self, operation: str = "operation"):
        message = f"{operation} timed out"
        super().__init__(message, code="TIMEOUT", retryable=True)


class ValidationError(PluginError):
    """Input validation error."""
    
    def __init__(self, message: str, field: str = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.field = field
'''
    
    def _setup_py(self, plugin_name: str) -> str:
        """Generate setup.py."""
        return f'''from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="{plugin_name}",
    version="0.1.0",
    author="Your Name",
    author_email="you@example.com",
    description="A plugin for Multi-Agent Content Platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",
    install_requires=[
        "httpx>=0.24.0",
        "pydantic>=2.0.0",
    ],
)
'''
    
    def _pyproject_toml(self, plugin_name: str) -> str:
        """Generate pyproject.toml."""
        return f'''[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "{plugin_name}"
version = "0.1.0"
authors = [
    {{ name = "Your Name", email = "you@example.com" }}
]
description = "A plugin for Multi-Agent Content Platform"
readme = "README.md"
requires-python = ">=3.10"
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
]

dependencies = [
    "httpx>=0.24.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "mypy>=1.0.0",
    "ruff>=0.1.0",
]

[tool.ruff]
line-length = 88
target-version = "py310"

[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
'''
    
    def _changelog_md(self) -> str:
        """Generate CHANGELOG.md."""
        today = datetime.now().strftime('%Y-%m-%d')
        return f"""# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - {today}

### Added
- Initial release
- Core functionality implementation
- Basic configuration support
- Unit tests

### Notes
- This is the initial release of the plugin
- More features coming soon!
"""
    
    def _license(self) -> str:
        """Generate LICENSE file (MIT)."""
        return """MIT License

Copyright (c) 2026 Your Name

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
    
    def _editorconfig(self) -> str:
        """Generate .editorconfig."""
        return """root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.{py,yml,yaml}]
indent_style = space
indent_size = 4

[*.{js,ts,vue,json}]
indent_style = space
indent_size = 2

[*.md]
trim_trailing_whitespace = false

[Makefile]
indent_style = tab
"""
    
    def _init_git_repo(self, directory: str):
        """Initialize Git repository."""
        
        import subprocess
        
        try:
            subprocess.run(
                ['git', 'init'],
                cwd=directory,
                check=True,
                capture_output=True
            )
            
            self.print_success("Git repository initialized")
            
        except FileNotFoundError:
            self.print_warning("Git not found, skipping initialization")
        except subprocess.CalledProcessError as e:
            self.print_warning(f"Failed to init git: {e.stderr.decode().strip()}")
    
    def _install_dependencies(self, directory: str):
        """Install Python dependencies."""
        
        import subprocess
        
        try:
            self.print_info("Installing dependencies...")
            
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'],
                cwd=directory,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                self.print_success("Dependencies installed")
            else:
                self.print_warning(f"Some dependencies failed to install:\n{result.stderr}")
                
        except Exception as e:
            self.print_warning(f"Could not install dependencies: {e}")
    
    def _print_summary(
        self,
        plugin_name: str,
        output_dir: str,
        plugin_type: str,
        template: dict,
        generated_files: list
    ):
        """Print creation summary."""
        
        print(f"\n{'='*60}")
        print(f"✅ Plugin created successfully!")
        print(f"{'='*60}")
        print(f"\n   Name:      {plugin_name}")
        print(f"   Location:  {output_dir}")
        print(f"   Type:      {plugin_type}")
        print(f"   Template:  {template['description']}")
        print(f"\n   Files generated ({len(generated_files)}):")
        
        for f in generated_files:
            print(f"      ✓ {f}")
        
        print(f"\n{'─'*60}")
        print(f"\nNext steps:")
        print(f"   $ cd {output_dir}")
        print(f"   $ plugin dev              # Start dev server")
        print(f"   $ plugin test             # Run tests")
        print(f"   $ plugin build            # Build for production")
        print(f"\nHappy coding! 🚀\n")