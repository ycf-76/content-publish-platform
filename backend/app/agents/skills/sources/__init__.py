"""多平台内容数据源抽象层。

与 mcp/ 目录并存：
- mcp/    — 小红书专用 MCP 客户端（保留，爬取能力）
- sources/ — 多平台内容源（Reddit、HackerNews、YouTube 等，统一接口）

设计原则：
1. 每个 source 只负责"拿数据"，返回统一的 TrendingContent
2. SourceManager 按 platform 名分发，工作流不关心数据来自哪个平台
3. 新增平台只需实现 ContentSource 接口 + 注册到 SourceManager
"""
