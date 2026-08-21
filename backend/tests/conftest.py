import sys
from pathlib import Path


# 确保 pytest 从任意目录运行时，backend/ 都在 sys.path 上，让 `import app.*` 可用。
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
