"""通过 SSE 监听验证 inject 后的事件流，看 image_review 是否收到 review_required。"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

OUTPUT_FILE = Path(r"d:\My_Project\多智能体小红书发布平台\backend\verify_events.txt")


async def main():
    lines = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # 监听 console 输出，捕获 SSE 事件
        sse_events = []

        def on_console(msg):
            text = msg.text
            if "workflow_snapshot" in text or "node_status_changed" in text or "node_completed" in text or "review_required" in text or "inject" in text.lower():
                sse_events.append(f"[{msg.type}] {text}")

        page.on("console", on_console)

        lines.append("[1] 访问 workbench")
        await page.goto("http://localhost:3001/workbench", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(2000)

        # 注入 console.log 拦截 SSE 事件
        await page.evaluate("""() => {
            if (window._sse_intercepted) return;
            window._sse_intercepted = true;
            window._sse_events = [];

            // 拦截 fetch 拦截 SSE
            const origFetch = window.fetch;
            window.fetch = async function(...args) {
                const resp = await origFetch.apply(this, args);
                const url = args[0]?.url || args[0] || '';
                if (typeof url === 'string' && url.includes('/sse')) {
                    // clone 后读取 stream
                    const cloned = resp.clone();
                    (async () => {
                        const reader = cloned.body.getReader();
                        const decoder = new TextDecoder();
                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) break;
                            const text = decoder.decode(value, { stream: true });
                            // 解析 SSE event 行
                            const lines = text.split('\\n');
                            let eventType = '';
                            let data = '';
                            for (const line of lines) {
                                if (line.startsWith('event:')) eventType = line.slice(6).trim();
                                else if (line.startsWith('data:')) data = line.slice(5).trim();
                            }
                            if (eventType && data) {
                                const evt = { event: eventType, data: data.substring(0, 200) };
                                window._sse_events.push(evt);
                                console.log(`SSE event: ${eventType} data=${data.substring(0, 100)}`);
                            }
                        }
                    })();
                }
                return resp;
            };
            console.log('SSE interceptor installed');
        }""")

        # 触发卡片编辑器显示并模拟 inject
        lines.append("[2] 触发卡片编辑器显示")
        result = await page.evaluate("""() => {
            const app = document.querySelector('#app');
            if (!app || !app.__vue_app__) return {error: 'no vue'};

            function findComp(instance, depth = 0) {
                if (!instance || depth > 30) return null;
                const s = instance.setupState || {};
                if ('workflowStore' in s && 'showCardEditor' in s) return instance;
                const subTree = instance.subTree;
                if (subTree) {
                    function walk(v) {
                        if (!v) return null;
                        if (v.component) {
                            const f = findComp(v.component, depth + 1);
                            if (f) return f;
                        }
                        if (v.children && Array.isArray(v.children)) {
                            for (const c of v.children) {
                                if (c && typeof c === 'object') {
                                    const f = walk(c);
                                    if (f) return f;
                                }
                            }
                        }
                        return null;
                    }
                    return walk(subTree);
                }
                return null;
            }

            const target = findComp(app.__vue_app__._instance);
            if (!target) return {error: 'no WorkbenchView'};

            const store = target.setupState.workflowStore;
            // 模拟工作流
            store.currentWorkflow = { workflow_id: 'test-inject-001', status: 'running' };
            store.nodes = [
                { node_id: 'search', node_type: 'search', status: 'completed' },
                { node_id: 'analyze', node_type: 'analyze', status: 'completed' },
                { node_id: 'copywrite', node_type: 'copywrite', status: 'completed' },
                { node_id: 'image_plan', node_type: 'image_plan', status: 'completed',
                  result: { card_draft: { suggested_template: 'minimal_white', pages: [
                      { type: 'cover', title: '测试', content: '测试内容' }
                  ]}}},
                { node_id: 'image_gen', node_type: 'image_gen', status: 'pending' },
                { node_id: 'image_review', node_type: 'image_review', status: 'pending' },
            ];
            return { success: true, nodeCount: store.nodes.length };
        }""")
        lines.append(f"  注入结果: {json.dumps(result, indent=2, default=str)}")
        await page.wait_for_timeout(2000)

        # 检查卡片编辑器是否显示
        editor_count = await page.locator(".wf-card-editor-host").count()
        lines.append(f"  卡片编辑器显示: {editor_count > 0}")

        # 模拟点击生成图片按钮（会调用 inject API，因为 workflow_id 不存在会失败，但能看到调用）
        lines.append("[3] 模拟点击生成图片按钮")
        btn = page.locator(".cep-gen-btn").first
        if await btn.count() > 0:
            await btn.click()
            await page.wait_for_timeout(3000)
            lines.append("  已点击")
        else:
            lines.append("  未找到按钮")

        # 获取 SSE 事件
        sse_result = await page.evaluate("""() => {
            return {
                events: (window._sse_events || []).slice(-30),
                totalEvents: (window._sse_events || []).length,
            };
        }""")
        lines.append(f"\n[4] SSE 事件 ({sse_result['totalEvents']} 总计):")
        for evt in sse_result['events']:
            lines.append(f"  {evt['event']}: {evt['data'][:120]}")

        # 检查前端节点状态
        node_states = await page.evaluate("""() => {
            const app = document.querySelector('#app');
            const target = (function findComp(instance, depth = 0) {
                if (!instance || depth > 30) return null;
                const s = instance.setupState || {};
                if ('workflowStore' in s && 'showCardEditor' in s) return instance;
                const subTree = instance.subTree;
                if (subTree) {
                    function walk(v) {
                        if (!v) return null;
                        if (v.component) return findComp(v.component, depth + 1) || (v.children && Array.isArray(v.children) ? v.children.map(walk).find(Boolean) : null);
                        return null;
                    }
                    return walk(subTree);
                }
                return null;
            })(app.__vue_app__._instance);
            if (!target) return null;
            const store = target.setupState.workflowStore;
            return store.nodes.map(n => ({ node_id: n.node_id, status: n.status }));
        }""")
        lines.append(f"\n[5] 前端节点状态:")
        lines.append(f"  {json.dumps(node_states, indent=2, default=str)}")

        # 检查 image_review 节点是否显示审核按钮
        review_btn_count = await page.locator("#card-image-review .wf-review-actions").count()
        lines.append(f"\n[6] image_review 审核按钮显示: {review_btn_count > 0}")

        await browser.close()

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Result written to {OUTPUT_FILE}")


asyncio.run(main())
