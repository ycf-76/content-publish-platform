"""
Hello World Plugin - 最简单的插件示例
======================================

这是一个教学用的最简插件，展示：
1. plugin.json 的基本结构
2. BaseWorkflowNodePlugin 的继承
3. execute() 方法的实现
4. NodeOutput 的返回格式
5. 配置的使用

适合：第一次学习插件开发的开发者
预计学习时间：30分钟
"""

import time
from datetime import datetime
from typing import Dict, Any, Optional

# 注意：在实际使用时，这些导入路径会根据你的项目结构调整
# 这里使用相对导入以便示例独立运行
try:
    from app.core.base_interfaces import BaseWorkflowNodePlugin, PluginContext, NodeOutput
    from app.core.plugin_types import PluginManifest, HealthStatus
except ImportError:
    # 开发模式下的模拟定义（实际项目中不需要）
    from dataclasses import dataclass, field
    from abc import ABC, abstractmethod
    from enum import Enum
    
    class HealthStatus:
        def __init__(self, status: str, message: str, timestamp: datetime = None, details: dict = None):
            self.status = status
            self.message = message
            self.timestamp = timestamp or datetime.utcnow()
            self.details = details or {}
    
    @dataclass
    class NodeOutput:
        success: bool
        data: Dict[str, Any] = field(default_factory=dict)
        message: str = ""
        execution_time_ms: int = 0
    
    @dataclass
    class PluginManifest:
        id: str
        name: str
        version: str
        category: str
        description: str
        capabilities: list
        permissions_required: list
    
    class PluginContext:
        def __init__(self):
            self.user_id = "anonymous"
            self.config: Optional[Dict] = None
            self.event_bus = None
            self.data_store = None
    
    class BaseWorkflowNodePlugin(ABC):
        id = ""
        name = ""
        version = "0.0.1"
        
        async def on_load(self): pass
        async def on_unload(self): pass
        
        @abstractmethod
        async def get_info(self) -> PluginManifest: pass
        
        @abstractmethod
        async def health_check(self) -> HealthStatus: pass
        
        @abstractmethod
        async def execute(self, ctx: PluginContext, inputs: Dict[str, Any]) -> NodeOutput: pass


class HelloWorldPlugin(BaseWorkflowNodePlugin):
    """
    Hello World 插件
    
    功能：
    - 接收一个名字作为输入
    - 根据配置生成个性化问候语
    - 可选包含时间戳和表情符号
    - 发出 greeting:generated 事件
    
    学习要点：
    1. 如何从 inputs 获取用户输入
    2. 如何从 ctx.config 读取配置
    3. 如何构建返回的 NodeOutput
    4. 如何发出事件通知其他插件
    """
    
    # ===== 类属性 =====
    id = "hello-world"
    name = "Hello World"
    version = "1.0.0"
    
    # 表情符号映射表
    EMOJI_STYLES = {
        "none": "",
        "friendly": "😊",
        "party": "🎉",
        "professional": "💼"
    }
    
    # 默认问候语模板（当config未设置时使用）
    DEFAULT_TEMPLATE = "Hello, {name}!"
    
    def __init__(self):
        """初始化插件实例"""
        super().__init__()
        self._load_count = 0  # 记录加载次数（用于演示状态管理）
        self._last_greeting = ""  # 缓存最后一次生成的问候语
    
    # ===== 生命周期方法 =====
    
    async def on_load(self) -> None:
        """
        插件加载时调用
        
        用途：
        - 初始化资源（连接池、缓存等）
        - 加载配置默认值
        - 预计算或预热数据
        """
        self._load_count += 1
        print(f"[{self.id}] Plugin loaded (#{self._load_count})")
        
        # 在真实场景中，这里可能会：
        # - 创建数据库连接池
        # - 初始化HTTP客户端
        # - 加载机器学习模型
        # - 建立缓存实例
    
    async def on_unload(self) -> None:
        """
        插件卸载时调用
        
        用途：
        - 清理资源
        - 持久化状态
        - 注销事件监听器
        """
        print(f"[{self.id}] Plugin unloading...")
        
        # 清理资源
        self._last_greeting = ""
    
    # ===== 必须实现的接口 =====
    
    async def get_info(self) -> PluginManifest:
        """
        返回插件元信息
        
        Returns:
            PluginManifest: 包含id/version/name等的完整信息
            
        说明：
        这个方法会被系统调用以获取插件的基本信息，
        用于在UI中展示、日志记录、权限检查等。
        """
        return PluginManifest(
            id=self.id,
            name=self.name,
            version=self.version,
            category="workflow_node",
            description="最简单的插件示例 - 生成个性化问候语",
            capabilities=["execute"],
            permissions_required=[]
        )
    
    async def health_check(self) -> HealthStatus:
        """
        健康检查
        
        Returns:
            HealthStatus: 包含status/message/timestamp
            
        说明：
        系统会定期调用此方法检查插件是否正常工作。
        返回的状态会显示在监控面板中。
        """
        is_healthy = True
        details = {}
        
        # 可以在这里添加自定义健康检查逻辑
        # 例如：检查外部服务是否可用、数据库是否连接正常等
        
        return HealthStatus(
            status="healthy" if is_healthy else "unhealthy",
            message="Ready to generate greetings",
            timestamp=datetime.utcnow(),
            details=details
        )
    
    # ===== 核心业务逻辑 =====
    
    async def validate_inputs(
        self, 
        inputs: Dict[str, Any]
    ) -> tuple[bool, str]:
        """
        验证输入参数
        
        Args:
            inputs: 用户提供的输入数据
            
        Returns:
            tuple[bool, str]: (是否有效, 错误信息)
            
        说明：
        在execute之前调用，用于提前验证输入合法性。
        如果返回False，execute将不会被调用。
        """
        
        # 检查必需字段
        if 'name' not in inputs:
            return False, "Missing required field: 'name'"
        
        name = inputs['name']
        
        # 验证name不为空
        if not name or not str(name).strip():
            return False, "Field 'name' cannot be empty"
        
        # 验证长度限制
        name_str = str(name).strip()
        if len(name_str) > 100:
            return False, f"Field 'name' too long (max 100 chars, got {len(name_str)})"
        
        # 验证不包含特殊字符（可选）
        # import re
        # if re.search(r'[\x00-\x1f\x7f-\x9f]', name_str):
        #     return False, "Field 'name' contains invalid characters"
        
        return True, "Inputs are valid"
    
    async def execute(
        self, 
        ctx: PluginContext, 
        inputs: Dict[str, Any]
    ) -> NodeOutput:
        """
        执行核心逻辑 - 生成问候语
        
        Args:
            ctx: 插件执行上下文，包含：
                - user_id: 当前用户ID
                - config: 用户/管理员配置
                - event_bus: 事件总线引用
                - data_store: 数据存储引用
                
            inputs: 输入数据，包含：
                - name (str): 要问候的名字
                
        Returns:
            NodeOutput: 执行结果，包含：
                - success: 是否成功
                - data: 输出数据字典
                - message: 人类可读的消息
                - execution_time_ms: 执行耗时
        """
        
        start_time = time.perf_counter()
        
        try:
            # ===== 步骤1: 验证输入 =====
            is_valid, error_msg = await self.validate_inputs(inputs)
            if not is_valid:
                return NodeOutput(
                    success=False,
                    data={},
                    message=f"Validation failed: {error_msg}",
                    execution_time_ms=0
                )
            
            # ===== 步骤2: 读取配置 =====
            config = ctx.config if ctx.config else {}
            
            # 获取模板（优先使用配置，否则用默认值）
            template = config.get(
                'greeting_template', 
                self.DEFAULT_TEMPLATE
            )
            
            # 是否包含时间戳
            include_timestamp = config.get(
                'include_timestamp', 
                True
            )
            
            # 表情符号风格
            emoji_style = config.get('emoji_style', 'friendly')
            emoji = self.EMOJI_STYLES.get(emoji_style, self.EMOJI_STYLES['friendly'])
            
            # ===== 步骤3: 处理业务逻辑 =====
            name = str(inputs['name']).strip()
            
            # 使用模板生成问候语
            greeting = template.format(name=name)
            
            # 添加表情符号
            if emoji:
                greeting = f"{greeting} {emoji}"
            
            # ===== 步骤4: 构建输出数据 =====
            output_data = {
                "greeting": greeting,
            }
            
            # 可选：添加时间戳
            if include_timestamp:
                output_data["timestamp"] = datetime.utcnow().isoformat()
            
            # 可选：添加元数据
            output_data["metadata"] = {
                "plugin_version": self.version,
                "input_name_length": len(name),
                "template_used": template
            }
            
            # 计算耗时
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            
            # ===== 步骤5: 发出事件（可选）=====
            if ctx.event_bus:
                await ctx.event_bus.emit(
                    "greeting:generated",
                    data={
                        "plugin_id": self.id,
                        "greeting": greeting,
                        "recipient_name": name,
                        "timestamp": datetime.utcnow().isoformat()
                    },
                    source=self.id
                )
            
            # 缓存结果（用于调试）
            self._last_greeting = greeting
            
            # ===== 步骤6: 返回成功结果 =====
            return NodeOutput(
                success=True,
                data=output_data,
                message=f"Greeting generated for '{name}' successfully",
                execution_time_ms=elapsed_ms
            )
            
        except Exception as e:
            # 统一错误处理
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            
            print(f"[ERROR] {self.id} execution failed: {e}")
            
            return NodeOutput(
                success=False,
                data={},
                message=f"Internal error: {str(e)}",
                execution_time_ms=elapsed_ms
            )


# ===== 测试代码（仅在本文件直接运行时执行）=====

if __name__ == "__main__":
    """
    本地测试入口
    
    当直接运行 python main.py 时，会执行简单的自测。
    这对于快速验证逻辑非常有用。
    """
    
    import asyncio
    
    async def test():
        """运行基本功能测试"""
        
        print("=" * 60)
        print("  Hello World Plugin - Local Test")
        print("=" * 60)
        
        # 创建插件实例
        plugin = HelloWorldPlugin()
        
        # 模拟上下文
        ctx = PluginContext()
        ctx.user_id = "test_user"
        ctx.config = {
            "greeting_template": "你好, {name}! 欢迎来到插件世界！",
            "include_timestamp": True,
            "emoji_style": "party"
        }
        
        # 测试1: 正常执行
        print("\n[Test 1] Normal execution:")
        result = await plugin.execute(ctx, {"name": "World"})
        print(f"  Success: {result.success}")
        print(f"  Greeting: {result.data.get('greeting')}")
        print(f"  Message: {result.message}")
        print(f"  Time: {result.execution_time_ms}ms")
        
        # 测试2: 自定义名字
        print("\n[Test 2] Custom name:")
        result2 = await plugin.execute(ctx, {"name": "Alice"})
        print(f"  Greeting: {result2.data.get('greeting')}")
        
        # 测试3: 验证失败（空名字）
        print("\n[Test 3] Validation failure (empty name):")
        result3 = await plugin.execute(ctx, {"name": ""})
        print(f"  Success: {result3.success}")
        print(f"  Message: {result3.message}")
        
        # 测试4: 健康检查
        print("\n[Test 4] Health check:")
        health = await plugin.health_check()
        print(f"  Status: {health.status}")
        print(f"  Message: {health.message}")
        
        # 测试5: 插件信息
        print("\n[Test 5] Plugin info:")
        info = await plugin.get_info()
        print(f"  ID: {info.id}")
        print(f"  Name: {info.name}")
        print(f"  Version: {info.version}")
        
        print("\n" + "=" * 60)
        print("  All tests completed!")
        print("=" * 60)
    
    # 运行异步测试
    asyncio.run(test())