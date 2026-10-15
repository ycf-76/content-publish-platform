# 前端编辑 UI 适配（第九轮 · 2026-10-06）

用户选定「前端编辑 UI 适配」收尾 P2：让 `ChatCardDraft.vue` 块级编辑 timeline 条目、quote 三锚点，以及 P0 的 note/tag、P1 的 bento/stat。只改 ReAct 相关前端组件，不动前端框架（Vue）。

## 关键修复：后端 HTTP 层曾静默丢弃新字段
后端 `operations.CardEdit` 早已支持 `note/tag/kicker/unit/source`，但 API 的 `CardEditRequest` 与 `_to_card_edit` **没有**这些字段。FastAPI 默认忽略请求体里的多余字段，导致前端发来的副行/标签/矩阵五层/金句锚点编辑**不报错但全部无效（no-op）。这是本次适配能否真正生效的决定性修复。

## 改动清单
- `backend/app/api/routers/creative_artifact.py`：`CardEditRequest` 增加 `note/tag/kicker/unit/source`（带 max_length），`_to_card_edit` 转发到 `CardEdit`。
- `frontend/src/components/chat/ChatCardDraft.vue`：
  - `editableBlocks` 白名单扩入 `bento_grid/stat/timeline/quote`；`BLOCK_LABELS`/`LAYOUT_LABELS` 补齐中英文名。
  - `editorMode` 新增 `bento/stat/timeline/quote` 分支与模板：timeline 三字段（`日期/标题/副行`）、quote 三锚点（`正文/作者/顶部标签`）、bento/stat 五层（`kicker/big/unit/note/source`，bento 多格时出格子选择器）。
  - `runEdit` 透传新字段；`saveItem/addItem` 携带 note/tag，并修复旧 `String(item)` 把清单项渲染成 `[object Object]` 的缺陷。
  - 主题下拉改消费 `themeOptions`（6 种全量可选）。
- `frontend/src/composables/cardDraft.ts`：`NormalizedCardDraft` 增 `themeOptions` 并透传（否则主题下拉为空）。
- `frontend/src/api/creativeArtifact.ts`：`CardEditPayload` 增 `note/tag/kicker/unit/source` 并透传。
- `backend/tests/test_card_edit_request_wiring.py`（新建）：6 个用例锁住「请求体 → CardEdit」透传。

## 字段映射妥协（前端显式映射，避免语义错乱）
| 块型 | op | 前端 → 后端 |
|---|---|---|
| timeline | set_timeline_item | `value=date`、`note=text`、`tag=note` |
| quote | set_quote | `value=text`、`note=author`、`tag=kicker` |
| bento/stat | set_bento_cell / set_stat_value | `value=big`、`kicker/unit/note/source` 同名 |
| list/steps | set_item | `value=text`、`note=note`、`tag=tag` |

## 验证
- 前端：`vue-tsc -b --force` 通过；`vite build` 通过。
- 后端：`test_react_structured_cards.py` + `test_artifact_store_safety.py` = 39 passed（与 P2 基线一致，零新增回归）；新增 wiring 测试 6 passed。
- 内联验证 `_to_card_edit` 对 timeline/bento/stat/quote/item 均正确转发新字段到 `CardEdit`。

## 仍未做
- P3 1:1 画幅逃生阀（1080×1080）。
- 真实 Wanx 生图 + 在线 ReAct→SSE→浏览器全链路冒烟。
- 前端尚未把每页 `density` 诊断做成"这一页太空"的红色提示。
