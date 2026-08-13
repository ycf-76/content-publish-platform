"""复用已有 cookies 创建新 worker 会话，导航到 /explore 提取用户信息。"""
import json
import time
import urllib.request

QR_ID = "qr_z7YlRRJTpANH5LLIyOSsSQ"
WORKER = "http://127.0.0.1:9010"


def worker(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body else b""
    req = urllib.request.Request(
        f"{WORKER}{path}",
        method=method,
        data=data if method in ("POST", "PUT", "DELETE") else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_eval(session_id: str, js: str) -> dict:
    req = urllib.request.Request(
        f"{WORKER}/debug_eval/{session_id}",
        method="POST",
        data=json.dumps({"js": js}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# 1. 导出当前会话 cookies
print("=== 1. 导出当前会话 cookies ===")
r = worker("POST", f"/cookies/{QR_ID}")
cookies = r.get("data", [])
print(f"cookies 数量: {len(cookies)}")

# 2. 用 cookies 创建新会话
print("\n=== 2. 用 cookies 创建新会话 ===")
r = worker("POST", "/session/create", {"cookies": cookies})
print(json.dumps(r, ensure_ascii=False, indent=2))
session_id = r.get("data", {}).get("session_id", "")
if not session_id:
    print("创建会话失败")
    exit(1)

# 3. 导航到 /explore
print(f"\n=== 3. 导航到 /explore (session={session_id}) ===")
# 用 debug_eval 让 page 自己 goto（但 debug_eval 只能 evaluate JS）
# 用 location.href 会让 page 重新加载，但 worker 的 page 对象应该能感知
# 改用 fetch + DOMParser 在内存里解析
js_nav = """async () => {
  // 先看当前 URL
  const before = location.href;
  // 用 fetch 拿 /explore 的 HTML，在内存里解析
  const resp = await fetch('https://www.xiaohongshu.com/explore', {
    credentials: 'include',
    headers: {'Accept': 'text/html'},
  });
  const html = await resp.text();
  // 找 window.__INITIAL_STATE__=
  const marker = 'window.__INITIAL_STATE__=';
  const idx = html.indexOf(marker);
  if (idx < 0) return {ok: false, error: 'no __INITIAL_STATE__', htmlLen: html.length, before: before};
  // 用 Function 构造器执行赋值语句（在沙箱里）
  const scriptEnd = html.indexOf('</script>', idx);
  const scriptContent = html.substring(idx, scriptEnd);
  // 用 new Function 执行
  try {
    // eslint-disable-next-line no-new-func
    const fn = new Function(scriptContent + '; return window.__INITIAL_STATE__;');
    const state = fn();
    // 遍历找 user 对象
    const users = [];
    const visited = new WeakSet();
    const findUsers = (o, path, dp) => {
      if (!o || typeof o !== 'object' || dp > 8 || visited.has(o)) return;
      visited.add(o);
      if (o.user_id && o.nickname) {
        users.push({
          path: path,
          user_id: o.user_id,
          nickname: o.nickname,
          image: o.image || o.images || o.imageb || '',
          images: o.images || '',
          imageb: o.imageb || '',
          red_id: o.red_id || o.redId || '',
        });
      }
      for (const [k, v] of Object.entries(o)) {
        findUsers(v, path + '.' + k, dp + 1);
      }
    };
    findUsers(state, '', 0);
    return {
      ok: true,
      before: before,
      topKeys: Object.keys(state),
      userSectionKeys: state.user && typeof state.user === 'object' ? Object.keys(state.user) : null,
      usersFound: users.length,
      users: users.slice(0, 8),
    };
  } catch(e) {
    return {ok: false, error: String(e), scriptHead: scriptContent.substring(0, 100)};
  }
}"""
r = call_eval(session_id, js_nav)
print(json.dumps(r, ensure_ascii=False, indent=2))
