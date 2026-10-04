---
node_type: produce
name: mindmap
category: create
priority: warm
display_name: 思维导图
description: >-
  把 Markdown 大纲渲染成可交互思维导图 HTML。适合知识结构、内容框架、
  SWOT、脑图梳理。和 infographic 的区别：infographic 做信息图/流程图，
  本 Skill 专做层级大纲思维导图。
trigger_words:
  - 思维导图
  - 脑图
  - mindmap
  - 知识导图
  - 大纲图
  - 把要点做成脑图
  - 内容结构图
  - SWOT图
  - 树状图
---

# 思维导图（mindmap）

> 把 Markdown 大纲渲染成可交互思维导图 HTML，基于 markmap 开源库。

## 输入

Markdown 大纲（用标题 `#`/`##`/`###` 表示层级，`-` 列表表示叶子）：
```markdown
# 中心主题
## 分支一
- 要点 A
- 要点 B
## 分支二
- 要点 C
```

或直接给一段文本/主题，由 LLM 提炼成大纲再渲染。

## 执行步骤

1. **提炼大纲**：如果输入是文本/主题而非大纲，先提炼成 Markdown 层级大纲
2. **生成 HTML**：用 markmap 库生成自包含 HTML（JS 走 CDN，可交互展开/折叠）
3. **输出**：用 `<!--card-html-->...<!--/card-html-->` 包裹，前端 iframe 渲染

## HTML 模板结构

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>/* 主题CSS */</style>
  <script src="https://cdn.jsdelivr.net/npm/markmap-autoloader@0.17"></script>
</head>
<body>
  <svg id="markmap" />
  <script>
    markmap.create('#markmap', null, `MARKDOWN_CONTENT`);
  </script>
</body>
</html>
```

## 平台适配

| 平台 | 推荐场景 | 交互引导 | 配合 Skill |
|------|---------|---------|-----------|
| 小红书 | 知识框架图/学习路线图/SWOT/内容策划 | "收藏备用" | xhs-note-creator |
| 抖音 | 视频脚本脑图/选题矩阵 | 评论区发完整版 | video-script |
| B站 | 知识体系/课程大纲/技术路线 | 简介区放链接 | article-outline |
| 公众号 | 文章大纲/知识框架/读书笔记 | "收藏+在看" | gzh-design |
| 知乎 | 知识体系/对比框架/决策树 | "赞同+收藏" | article-outline |

**通用建议**：脑图收藏率比纯文字高 3-5 倍，适合干货内容可视化

## 规则

1. 层级建议 2-4 层，节点文字精炼（几个字），别把整句话塞进节点
2. 每个分支不超过 7 个子节点（认知负荷限制）
3. HTML 必须是完整文档（含 DOCTYPE/html/head/body）
4. 用 `<!--card-html-->` 标记包裹，不用 ```html 代码块