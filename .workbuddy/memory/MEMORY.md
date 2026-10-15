# 项目长期约定

## 代码型 Skill 的位置（2026-10-10 重构后，别再用旧路径）

- 基类 / 注册表 / 路由器：`app/core/skill_base.py`、`app/core/skill_registry.py`、`app/core/skill_router.py`
- 内置代码型 Skill：`app/skills/` 包（`app/skills/produce/tts.py` 等）
- **`app/tools/base.py`、`app/tools/registry.py`、`app/tools/card_compose.py`、
  `app/tools/card_image_gen.py`、`app/tools/prompt_skills.py` 已全部不存在** → 新 Skill 别 import 它们
- `app/tools/` 只剩 `viral_analyzer.py` 和 `browser/`、`sources/` 子包

## 排查「Agent 说没有 X 能力」（固定套路，按顺序查）

工具表链路：
`SkillRegistry`（@register 注册）→ `_build_skills(agent_def.skills, creation_type)`（过滤）
→ `harness.skills` → `LoopExecutor._build_tools_schema()`（转 function calling）
→ **截断到 `_MAX_TOOLS_FOR_LLM = 65`，顺序 triggered→hot→warm→cold**。

逐环排查：
1. **装没装上**：ImportError 会让 `@register` 不执行，Skill 根本不进注册表。
   用 `.venv/Scripts/python.exe -c "import <skill module>"` 验证依赖齐全（缺 `edge_tts` 就让 TTS 消失过）。
2. **统计全量时必须跑 `registry.scan_third_party()`** —— 只 import `BUILTIN_SKILL_MODULES` 只有 25 个，
   真实全量是 **90** 个（含 `backend/skills/` 第三方扫描）。别拿 25 当全量做判断。
3. **白名单排序（2026-10-11 已重构，不再是过滤器）**：`app/agents/registry.py` 的
   `CREATION_TYPE_SKILLS` 现在**只排序不过滤**——命中的排前面，其余跟上，保证都加载。
   漏配的后果从"静默消失"降级为"丧失排序优先级"（65 截断时先被牺牲）。
   覆盖 55 个名字 vs 注册 90 个 → 35 个孤儿只丧失优先级，仍可见。
   `_audit_skill_coverage()` 会双向审计：漏配告警 + 白名单里的幽灵名（拼错/已改名）。
4. **65 上限截断**：hot 37 / warm 36 / cold 17。90 个会截到 65，cold 全砍、warm 按队列顺序截取。
   保命手段：① trigger_words 命中进 triggered 队列（优先级最高）
   ② 白名单命中排前（各优先级段内靠前，warm 截断时能保住）
   ③ 把 priority 提到 hot。
   **注意 triggered 曾长期失效**（见下）。
5. **验证**：`LoopExecutor.__new__(LoopExecutor)` 绕过 `__init__`（避免拉 LLM），
   手动塞 `_routing_result=None; _tools_schema_cache=None; _skill_router=SkillRouter(max_tools=65)`，
   再用假 harness 调 `_build_tools_schema()` 就能拿到 Agent 真实工具表，对每个 creation_type 都测一遍。
   要测 triggered 保命，先手动 `ex._routing_result = ex._skill_router.select_skills(skills, 用户消息)`。

### 已修：triggered 队列曾是死代码（`app/engine/harness/executor/loop.py`）

`execute()` 里 `_build_tools_schema()` 先跑并缓存进 `_tools_schema_cache`，
而路由在 L1188 才执行 → 建表时 `_routing_result` 永远 None → triggered 队列永远空
→ trigger_words 的"点名保命"完全失效。已把 `select_skills()` 前移到建表之前。
**以后改 executor 执行顺序时，任何"先于路由"的建表/建 catalog 都会让 triggered 失效。**

## 前端样式作用域（重要，踩过坑）

`frontend/src/components/chat/chat-view.css` 通过 `<style scoped src="./chat-view.css">` 引入，**是 scoped 的**。

后果：任何落在**子组件内部节点**或 **v-html 渲染内容**上的类名，写在这个文件里**不生效**——
编译后变成 `.xxx[data-v-hash]`，而子组件的根节点之外的内部元素拿不到这个属性
（Vue 只把父组件 scope id 加到子组件**根节点**上）。

典型受害者：
- `.dsh-md` 全套 markdown 样式 → 必须写在 `ChatView.vue` 的**全局 `<style>` 块**（L1633 起）
- `.dsh-streaming-light`（落在 AssistantMessageCell 内部）→ 原本写在 scoped 文件里，一直是死样式，2026-10-06 已迁到全局块

**规则**：给 v-html 内容或子组件内部节点写样式 → 用 `ChatView.vue` 的全局 `<style>` 块；
只作用于 ChatView 自己模板节点的样式 → 放 `chat-view.css`。

**改 markdown 配色要同时改两处**：ChatView.vue 全局块（真生效）+ chat-view.css 里的
`.dsh-assistant-content :deep(...)` 副本（当前不生效，但留着旧色是隐患，文件内已标注）。
markdown 静态描边统一走变量 `--dsh-md-rule` / `--dsh-md-quote-bg`（定义在 `.dsh-chat`，亮暗两套）。

## 后端运行环境（重要，2026-10-07 实测，别再搞混）

- **服务只能用 `backend/.venv/Scripts/python.exe` 启动**。系统 `C:\Python312` **缺 `pydantic_settings`**，
  uvicorn 直接 `ModuleNotFoundError` 起不来（它虽然装了 scrapling 0.4.15）。
- `.venv` 有 fastapi / playwright 1.61 / playwright_stealth 2.0.3 / uvicorn / pydantic_settings，
  **但没有 scrapling**（采集链路 `app/platform_spider/*` 因此 import 失败）。
- 启动命令：
  `cd backend && ./.venv/Scripts/python.exe -u -m uvicorn app.main:app --host 0.0.0.0 --port 8000`
  **必须加 `-u`**：不加的话 stdout 重定向到文件是全缓冲，日志文件 0 字节，看着像没启动。
- 启动耗时 **100–120 秒**，日志到 `[lifespan] step 6` 之后才落盘，别 60 秒就判失败。
- 日志落 `backend/logs/`；端口 8000；前端 3001。
- 停服：杀所有命令行含 `uvicorn` / `spawn_main` 的 python.exe（PowerShell `Stop-Process -Force`，
  Git Bash 下 `taskkill //F` 会被当非法参数）。

## 构建

- `npm run build` = `vue-tsc -b && vite build`，直接清空 `dist/` 会被安全策略的批量删除拦截（>50 文件）。
- 需要冒烟验证时用 Vite JS API：`build({ build: { outDir: '临时目录', emptyOutDir: false } })`，别用 CLI。
- 临时构建目录用完要清，但删除请求可能被安全策略拦下并弹给大哥确认——**别反复重试**，交给他人为处理。

## 工具名中文映射只有一张表：`icon-map.ts`

`TOOL_ICON_MAP` 是「工具名 → 中文标签」的**唯一中心表**，`getToolDisplayLabel()` / `getToolIcon()` 都读它；
未命中时兜底返回原始工具名（历史上因此出现过「正在bash…」这种中英混杂文案）。

**任何组件里都不要再自己维护局部映射表** —— ToolCallCell 曾维护过一份，与中心表不一致导致
`xhs_search` 等 key 在一处有中文、另一处没有。新增工具一律直接往 `icon-map.ts` 补。

## 聊天流式渲染链路

- 流式 HTML 唯一出口：`components/chat/chat-content-renderer.ts` 的 `wrapStreamHtml()`
- 三态：preview（流式）→ settling → settled；settled 后 `msg._streamHtml` 仍保留并继续走 `wrapStreamHtml`，
  所以任何「只在流式时生效」的注入必须靠显式开关参数，不能无条件注入。
- 消息滚动容器：`.dsh-scroll-body`（`scrollBodyRef`）；面板根：`.dsh-chat`（`chatRootRef`）

## 小红书发布页的两个硬约束（实测，改发布逻辑前必读）

1. **必须用 `?target=image` 进图文模式**：`/publish/publish` 默认停在「上传视频」tab，
   非激活 tab 的内容被站点挪到**负坐标**（rect.x≈-9726，不是 display:none），
   Playwright 的 actionability 检查永远不过，打开后再点 tab 切换必然超时。
2. **填表顺序：传图 → 标题 → 正文 →（可选）点发布**。图文的标题输入框与正文
   contenteditable 是**图片上传成功后才渲染**的；先填标题必然全失配（实测 ce=0、inputs=[]）。

登录态：`qr_worker` 扫码写到 `app/storage_states/*.json`，发布会话启动时由
`PublisherSession._migrate_storage_cookies()` 自动迁进持久化 profile（幂等）。
**新扫码的 cookie 有效，隔几天的旧 cookie 无效**（web_session 绑设备指纹）。

## 内置浏览器事件模型约定（违反会大面积失效）

**凡是要模拟点击 / 输入 / 按键，一律走 `page.mouse.*`、`page.keyboard.*`、`locator.*`；
禁止 `page.evaluate` + `elementFromPoint().dispatchEvent(...)` 合成 DOM 事件。**

理由：合成事件 `isTrusted=false`，且没有 mousedown→mouseup→focus 序列，导致
下拉选项、日期选择器、hover 才渲染的菜单、`<select>`、`contenteditable` 工具栏全部打不中，
还会被站点风控识别为自动化。只有**读**操作（取文本、算坐标）才用 `evaluate`。

相关：`app/tools/browser/client.py`（BrowserClient 单例）、`app/api/routers/browser.py`（REST + MCP）。

2026-10-07 已补齐（别再退回 dispatchEvent）：`client.interact()` 封装原生输入；
`snapshot()` 扫描可交互元素注入 `data-bu-ref`、产出 `e0/e1/...` + `nav_seq`；
`act()` 支持 ref 编号并校验 nav_seq（不符返回 `STALE_SNAPSHOT`）；
坐标点击走 `elementFromPoint` 反查 → `locator.click`。路线选择：跟 Playwright MCP，
不追 Computer Use；截图保留给人看，a11y+ref 给模型用（双通道）。

## tool_call 事件配对规则（踩过坑）

`useChatSSE.ts` 的 `tool_call_start` / `tool_call_end` 必须按 **(工具名 + sub_agent_id) 严格配对**，
且只匹配**最早的那条仍为 running 的调用**（FIFO）。

**不要用「先取最后一个 toolCall，名字不符再回退搜索」的捷径** —— 多个子智能体并发调用同名工具时
（典型：两个子智能体都调 `trending_search`），结束事件会被记到隔壁子智能体头上，
真正发起的那条永远卡在 `running`，表现为「流程早已结束，顶部状态行却一直转圈说正在搜索」。

另外：任何**确定性终止**路径（`workflow_error` / `workflow_cancelled` / `agent_error` / SSE 重试耗尽）
都必须调用 `_settleOrphanToolCalls()` 清算残留的 running，否则会出现幽灵转圈。
终态用 `'aborted'` 而非 `'error'` —— 语义是「结果没回传，不知道成没成」，不该混进「遇到问题」的统计。
**不要**在 `workflow_completed` 上清算（chat 模式下 workflow 结束 ≠ 本轮工具调用结束），
也不要在 AbortError 上清算（会话切换/组件卸载会误伤）。
