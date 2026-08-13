"""通过真实 SSE 订阅验证 inject 后的事件流。"""
import asyncio
import json
from pathlib import Path
import httpx

OUTPUT_FILE = Path(r"d:\My_Project\多智能体小红书发布平台\backend\verify_sse.txt")

# 创建一个测试工作流
async def main():
    lines = []

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30) as client:
        # 1. 创建工作流
        lines.append("[1] 创建测试工作流")
        try:
            resp = await client.post("/api/workflows", json={
                "topic": "测试卡片编辑器inject",
                "user_id": "01H5GJ8R2K3M4N5P6Q7R8S9T0V",
                "account_id": "test",
            })
            wf_data = resp.json()
            lines.append(f"  响应: {wf_data}")
            wf_id = wf_data.get("data", {}).get("workflow_id", "")
            if not wf_id:
                # 尝试其他字段
                wf_id = wf_data.get("workflow_id", "") or wf_data.get("id", "")
            lines.append(f"  workflow_id: {wf_id}")
        except Exception as e:
            lines.append(f"  创建失败: {e}")
            OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
            return

        if not wf_id:
            lines.append("  无法获取 workflow_id，退出")
            OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
            return

        # 2. 订阅 SSE
        lines.append(f"\n[2] 订阅 SSE: {wf_id}")
        sse_events = []

        async def listen_sse():
            try:
                async with client.stream("GET", f"/api/workflows/{wf_id}/sse") as resp:
                    async for line in resp.aiter_lines():
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_str = line[5:].strip()
                            try:
                                data = json.loads(data_str)
                            except:
                                data = {"raw": data_str[:200]}
                            sse_events.append({"event": event_type, "data": data})
                            if event_type in ("workflow_completed", "workflow_failed", "workflow_error"):
                                return
                            if len(sse_events) > 100:
                                return
            except Exception as e:
                lines.append(f"  SSE 监听错误: {e}")

        # 启动 SSE 监听任务
        sse_task = asyncio.create_task(listen_sse())
        await asyncio.sleep(2)

        # 3. 手动注入图片（绕过卡片编辑器）
        lines.append(f"\n[3] 直接调用 inject-card-images")
        try:
            # 先模拟 image_plan 完成，通过 update_state
            # 但我们没有直接 update_state 的接口，只能通过 inject-card-images
            # inject 会检查 next 必须包含 image_gen
            # 所以工作流必须先执行到 image_gen 前 interrupt
            # 这里直接调 inject 看错误信息
            resp = await client.post(f"/api/workflows/{wf_id}/inject-card-images", json={
                "images_base64": ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="],
                "style": "测试",
            })
            inject_resp = resp.json()
            lines.append(f"  响应状态: {resp.status_code}")
            lines.append(f"  响应: {json.dumps(inject_resp, indent=2, default=str)[:500]}")
        except Exception as e:
            lines.append(f"  调用失败: {e}")

        # 等待 SSE 事件
        await asyncio.sleep(5)

        # 取消 SSE 监听
        sse_task.cancel()
        try:
            await sse_task
        except:
            pass

        lines.append(f"\n[4] 收到 SSE 事件 ({len(sse_events)} 条):")
        for i, evt in enumerate(sse_events[-30:]):
            event_type = evt["event"]
            data = evt["data"]
            # 简化 data 显示
            if "node_statuses" in data:
                summary = f"node_statuses={data['node_statuses']}"
            elif "status" in data and "node_id" in data:
                summary = f"node_id={data['node_id']}, status={data['status']}"
            elif "review_node" in data:
                summary = f"review_node={data['review_node']}"
            elif "images_base64" in data:
                summary = f"node_id={data.get('node_id')}, images={len(data['images_base64'])}"
            elif "message" in data:
                summary = f"message={data['message'][:100]}"
            else:
                summary = json.dumps(data, default=str)[:150]
            lines.append(f"  [{i}] {event_type}: {summary}")

    OUTPUT_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(f"Result written to {OUTPUT_FILE}")


asyncio.run(main())
