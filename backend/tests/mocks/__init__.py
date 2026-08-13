"""Mock 外部依赖（Phase 7 Part C）。

提供 4 个 mock：
- mock_deepseek: 返回固定 LLM 响应（含 reasoning_content 模拟 R1）
- mock_qwen_vl: 返回固定图片标签
- mock_mcp: 返回固定的小红书笔记数据（10 条 mock）
- mock_image_gen: 返回 1x1 PNG bytes

通过 monkeypatch / dependency injection 替换真实 adapter。
"""
