import sys, json, base64, secrets, os, time
from datetime import datetime, timedelta, timezone
from playwright.sync_api import sync_playwright

PLAYWRIGHT_BROWSERS_PATH = os.environ.get('PW_PATH', '')
if PLAYWRIGHT_BROWSERS_PATH:
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = PLAYWRIGHT_BROWSERS_PATH

_pw = None
_browser = None

def ensure_browser():
    global _pw, _browser
    if _browser:
        return _browser
    _pw = sync_playwright().start()
    _browser = _pw.chromium.launch(headless=True,
        args=['--no-sandbox'])
    return _browser

def generate_qrcode():
    browser = ensure_browser()
    ctx = browser.new_context(viewport={'width':1280,'height':800})
    page = ctx.new_page()
    try:
        page.goto('https://www.xiaohongshu.com/login', timeout=30000)
        page.wait_for_timeout(3000)
        qr_id = 'qr_' + secrets.token_urlsafe(16)
        exp = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        qr_b64 = ''
        for sel in ['img.qrcode-img','canvas','img[class*=qrcode]','.qrcode img','svg']:
            el = page.query_selector(sel)
            if el:
                d = el.screenshot()
                qr_b64 = 'data:image/png;base64,' + base64.b64encode(d).decode()
                break
        if not qr_b64:
            ss = page.screenshot(full_page=True)
            qr_b64 = 'data:image/png;base64,' + base64.b64encode(ss).decode()
        return {'qr_id':qr_id, 'qrcode_base64':qr_b64, 'expires_at':exp}
    finally:
        ctx.close()

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'qrcode':
        print(json.dumps(generate_qrcode()))
    else:
        print(json.dumps({'error':'unknown cmd:'+cmd}))