"""读 userInfo._value（Vue ref 的真实值）。"""
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


# userInfo 是 ref，真实值在 _value 或 .value
js = """() => {
  const ui = window.__INITIAL_STATE__?.user?.userInfo;
  if (!ui) return {ok: false, error: 'no userInfo'};
  // Vue ref: 真实值在 _value（或 .value getter）
  const val = ui._value || (typeof ui.value !== 'undefined' ? ui.value : null);
  if (!val) return {ok: false, error: 'no _value', uiKeys: Object.keys(ui)};
  // 提取简单字段
  const simple = {};
  for (const [k, v] of Object.entries(val)) {
    const t = typeof v;
    if (t === 'string' || t === 'number' || t === 'boolean' || v === null) {
      simple[k] = v;
    } else if (t === 'object' && v !== null) {
      simple[k] = '[obj: ' + Object.keys(v).slice(0, 5).join(',') + ']';
    } else {
      simple[k] = '[' + t + ']';
    }
  }
  return simple;
}"""
r = call_eval(js)
print(json.dumps(r, ensure_ascii=False, indent=2))

# 也看 loggedIn._value
js2 = """() => {
  const u = window.__INITIAL_STATE__?.user;
  const li = u?.loggedIn;
  const val = li && (li._value !== undefined ? li._value : li.value);
  return {loggedInValue: val};
}"""
r2 = call_eval(js2)
print("\nloggedIn value:")
print(json.dumps(r2, ensure_ascii=False, indent=2))
