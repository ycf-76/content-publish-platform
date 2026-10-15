# 项目协作约定

- 用户讨论“React 模块”的卡片生成问题时，优先理解为后端 **ReAct 对话式 Agent**（ChatAgent/LoopExecutor/图文 Skills），不要未经确认把 LangGraph/DAG 工作流作为主要分析对象。当前前端技术栈为 Vue，注意与 React UI 框架区分。
- 卡片方案应基于真实代码完整追踪、明确已实现/断链/仅规划的边界，优先给可落地的系统设计，而不是孤立补丁或仅换色模板。
- 结构化卡片（`backend/app/cards/`）以 CardDeck 为唯一事实源，HTML 只是渲染器编译出的预览；模型只输出受校验的语义 JSON，不输出 CSS/HTML。图片必须引用当前用户资产，卡片读写一律 owner-scoped，越权统一返回 404。
- 工作区存在大量与本轮需求无关的既有未提交漂移，并导致约 25 个后端测试失败（chat_agent、clarification、codex、loop smoke、sandbox 等）。改动前先跑一次基线确认，不要把这些既有失败算到自己头上，也不要擅自清理。
