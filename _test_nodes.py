import urllib.request
import json

wf_id = "01M0JG5C73QE9H3W9922GMB70V"
url = f"http://127.0.0.1:8000/api/v1/workflow/{wf_id}/nodes"
try:
    resp = urllib.request.urlopen(url, timeout=15)
    data = json.loads(resp.read())
    print(f"workflow_status: {data.get('data', {}).get('status')}")
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
    print(f"ERROR: {e}")