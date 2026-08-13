"""dump userInfo 的所有字段。"""
import json
import urllib.request

SESSION_ID = "sess_Oz7uH1qYaFnhGPsO8UFc3Q"
WORKER = "http://127.0.0.1:9010"


def call_eval(js: str) -> dict:
    req = urllib.request.Request(
        f"{WORKER}/debug_eval/{SESSION_ID}",
        method="POST",
        data=json.dumps({"js": js}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


js = """() => {
  const ui = window.__INITIAL_STATE__?.user?.userInfo;
  if (!ui) return {ok: false, error: 'no userInfo'};
  // 提取所有非函数、非对象字段
  const simple = {};
  for (const [k, v] of Object.entries(ui)) {
    const t = typeof v;
    if (t === 'string' || t === 'number' || t === 'boolean' || v === null) {
      simple[k] = v;
    } else if (t === 'object') {
      simple[k] = '[object]';
    } else {
      simple[k] = '[' + t + ']';
    }
  }
  return simple;
}"""
r = call_eval(js)
print(json.dumps(r, ensure_ascii=False, indent=2))

# 也看下 login section
js2 = """() => {
  const lg = window.__INITIAL_STATE__?.login;
  if (!lg) return {ok: false, error: 'no login section'};
  const simple = {};
  for (const [k, v] of Object.entries(lg)) {
    const t = typeof v;
    if (t === 'string' || t === 'number' || t === 'boolean' || v === null) {
      simple[k] = v;
    } else if (t === 'object') {
      simple[k] = '[object keys: ' + Object.keys(v).join(',') + ']';
    } else {
      simple[k] = '[' + t + ']';
    }
  }
  return simple;
}"""
r2 = call_eval(js2)
print("\nlogin section:")
print(json.dumps(r2, ensure_ascii=False, indent=2))
