import urllib.request
import json

# Test 1: health check
try:
    resp = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5)
    print(f"Health: {resp.status}")
except Exception as e:
    print(f"Health ERROR: {e}")

# Test 2: nodes endpoint
wf_id = "01M0JG5C73QE9H3W9922GMB70V"
try:
    resp = urllib.request.urlopen(f"http://127.0.0.1:8000/api/workflows/{wf_id}/nodes", timeout=10)
    data = json.loads(resp.read())
    print(f"Nodes OK, workflow_status={data.get('data', {}).get('status')}")
    nodes = data.get('data', {}).get('nodes', [])
    for n in nodes:
        nid = n.get('node_id', '?')
        st = n.get('status', '?')
        has_output = 'output' in n and bool(n['output'])
        output_keys = list(n.get('output', {}).keys())[:5] if has_output else []
        cp = n.get('output', {}).get('content_plan')
        has_cp = bool(cp) if cp else False
        print(f"  {nid}: status={st}, has_output={has_output}, has_content_plan={has_cp}, output_keys={output_keys}")
except Exception as e:
    print(f"Nodes ERROR: {e}")