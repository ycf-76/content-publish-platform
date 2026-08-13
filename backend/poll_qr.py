"""轮询二维码状态直到确认登录或过期。"""
import json
import sys
import time
import urllib.request

QR_ID = "qr_C_I6oYdjEODoPY1JV9uTpw"
URL = f"http://127.0.0.1:8007/api/accounts/qrcode/{QR_ID}/poll"


def poll_once() -> dict:
    req = urllib.request.Request(URL, method="POST", data=b"", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    print(f"轮询 qr_id={QR_ID}")
    print("-" * 60)
    max_attempts = 80
    for i in range(1, max_attempts + 1):
        try:
            r = poll_once()
            data = r.get("data", {})
            status = data.get("status", "unknown")
            msg = data.get("message", "")
            print(f"[{i:3d}] status={status}  msg={msg}")
            if status in ("confirmed", "expired", "failed", "error"):
                print("-" * 60)
                print(json.dumps(r, ensure_ascii=False, indent=2))
                return 0 if status == "confirmed" else 1
        except Exception as e:
            print(f"[{i:3d}] error: {e}")
        time.sleep(3)
    print("超时退出")
    return 1


if __name__ == "__main__":
    sys.exit(main())
