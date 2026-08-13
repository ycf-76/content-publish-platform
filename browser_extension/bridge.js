// bridge.js - 扩展内桥接页面逻辑
//
// 通信链路：
//   后端 SSE /api/mcp/bridge/stream  →  本页面  →  chrome.runtime.sendMessage  →  background.js
//   background.js 返回结果           →  本页面  →  POST /api/mcp/bridge/result/{call_id}  →  后端
//
// 本页面是扩展的一部分（chrome-extension://extensionId/bridge.html），
// 可直接用 chrome.runtime.sendMessage 不需要 extensionId。

const $ = (id) => document.getElementById(id);
const logEl = $("log");

function log(msg, level = "info") {
  const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  const line = document.createElement("div");
  line.className = `log-${level}`;
  line.textContent = `[${time}] ${msg}`;
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
  // 限制日志数量
  while (logEl.children.length > 200) {
    logEl.removeChild(logEl.firstChild);
  }
}

let eventSource = null;
let reconnectTimer = null;

function setDot(state, text) {
  const dot = $("bridge-dot");
  dot.className = `dot ${state}`;
  $("bridge-status").textContent = text;
}

function getBackendUrl() {
  return $("backend-url").value.replace(/\/+$/, "");
}

// 注册桥接页面在线状态
async function registerBridge() {
  const url = getBackendUrl() + "/api/mcp/bridge/register";
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page: "bridge" }),
    });
    if (resp.ok) {
      log("桥接页面注册成功", "success");
    } else {
      log(`注册失败: HTTP ${resp.status}`, "error");
    }
  } catch (e) {
    log(`注册失败: ${e.message}`, "error");
  }
}

// 回传结果给后端
async function postResult(callId, result) {
  const url = getBackendUrl() + `/api/mcp/bridge/result/${callId}`;
  try {
    await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(result),
    });
  } catch (e) {
    log(`回传结果失败: ${e.message}`, "error");
  }
}

// 处理后端推来的 MCP 请求
async function handleRequest(req) {
  const { call_id, action, payload } = req;
  log(`收到请求: action=${action} call_id=${call_id}`, "info");

  try {
    // 转发给扩展 background.js
    const result = await chrome.runtime.sendMessage({
      action,
      payload,
    });

    if (result && result.success) {
      log(`请求成功: action=${action}`, "success");
      await postResult(call_id, { success: true, data: result.data });
    } else {
      const msg = result?.message || "扩展返回失败";
      log(`请求失败: action=${action} → ${msg}`, "warn");
      await postResult(call_id, { success: false, message: msg });
    }
  } catch (e) {
    log(`转发异常: action=${action} → ${e.message}`, "error");
    await postResult(call_id, { success: false, message: e.message });
  }
}

// SSE 连接后端
function connectSSE() {
  if (eventSource) {
    eventSource.close();
  }
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  const url = getBackendUrl() + "/api/mcp/bridge/stream";
  log(`正在连接后端 SSE: ${url}`, "info");
  setDot("waiting", "正在连接后端...");

  eventSource = new EventSource(url);

  eventSource.onopen = async () => {
    log("SSE 连接已建立", "success");
    setDot("online", "桥接页面在线");
    await registerBridge();
  };

  eventSource.onmessage = async (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "hello") {
        log(`收到 hello: ${msg.message}`, "info");
        return;
      }
      if (msg.type === "request" && msg.call_id) {
        await handleRequest(msg);
        return;
      }
      log(`收到消息: ${JSON.stringify(msg).slice(0, 200)}`, "info");
    } catch (e) {
      log(`消息解析失败: ${e.message}`, "error");
    }
  };

  eventSource.onerror = (e) => {
    log("SSE 连接断开，5 秒后重连...", "error");
    setDot("offline", "连接断开，重连中...");
    eventSource.close();
    eventSource = null;
    reconnectTimer = setTimeout(connectSSE, 5000);
  };
}

// 定时心跳（每 30 秒重新注册，防止后端认为桥接页面离线）
setInterval(() => {
  if (eventSource && eventSource.readyState === EventSource.OPEN) {
    registerBridge();
  }
}, 30000);

// 重新连接按钮
$("btn-reconnect").addEventListener("click", () => {
  log("手动重连...", "info");
  connectSSE();
});

// 启动
log("桥接页面启动", "info");
connectSSE();
