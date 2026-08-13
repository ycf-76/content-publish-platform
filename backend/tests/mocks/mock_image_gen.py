"""Mock image generation adapter.

返回 1x1 PNG bytes。
不连真实通义万相 / 即梦 API。
"""

from __future__ import annotations

import base64
import binascii

from app.agents.adapters.image_gen import ImageGenAdapter


# 1x1 透明 PNG 的 base64（标准 PNG 签名 + IHDR + IDAT + IEND）
_TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _tiny_png_bytes() -> bytes:
    """返回 1x1 PNG bytes（已验证合法 PNG 签名）。"""
    return base64.b64decode(_TINY_PNG_B64)


class MockImageGenAdapter(ImageGenAdapter):
    """Mock 图片生成 adapter，返回 1x1 PNG。

    用法：
        adapter = MockImageGenAdapter()
        images = await adapter.generate("prompt", "1024x1024", 4)
        # images 是 4 个相同的 1x1 PNG bytes
    """

    def __init__(self, model: str = "mock-image-gen") -> None:
        self.model = model
        self._call_count = 0

    async def generate(
        self, prompt: str, size: str = "1024x1024", count: int = 1
    ) -> list[bytes]:
        """返回 count 个 1x1 PNG bytes。"""
        self._call_count += 1
        png = _tiny_png_bytes()
        return [png for _ in range(max(1, count))]


def install_mock_image_gen() -> MockImageGenAdapter:
    """构造 MockImageGenAdapter 实例。"""
    return MockImageGenAdapter()


def verify_tiny_png() -> bool:
    """校验 1x1 PNG 是否合法（前 8 字节是 PNG 签名）。"""
    png = _tiny_png_bytes()
    # PNG 文件签名：89 50 4E 47 0D 0A 1A 0A
    expected_sig = binascii.unhexlify("89504e470d0a1a0a")
    return png[:8] == expected_sig
