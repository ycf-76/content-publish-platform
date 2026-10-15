"""Export the same compiled HTML used for chat preview using a local Chromium."""

from __future__ import annotations

import os
from pathlib import Path

from app.cards.schema import CardDeck, ImageBlock
from app.cards.renderer import render_page
from app.services.asset_library import _path_from_url


async def render_png_pages(deck: CardDeck, user_id: str) -> list[bytes]:
    """Render verified, owner-scoped card assets. Never navigate to external URLs."""
    from app.cards.operations import verify_assets

    await verify_assets(deck, user_id)
    from playwright.async_api import async_playwright

    browser_path = os.getenv("CARD_CHROMIUM_PATH", "").strip()
    if not browser_path:
        bundled = Path(__file__).resolve().parents[3] / "pw-browsers " / "chromium-1228" / "chrome-win64" / "chrome.exe"
        if bundled.is_file():
            browser_path = str(bundled)
    if browser_path and not Path(browser_path).is_file():
        raise RuntimeError("CARD_CHROMIUM_PATH 指向的浏览器不存在")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=browser_path or None,
            headless=True,
        )
        try:
            context = await browser.new_context(
                viewport={"width": deck.width, "height": deck.height}, device_scale_factor=1,
            )
            async def serve_local_asset(route):
                url = route.request.url
                if url.startswith("http://card.local/uploads/"):
                    path = _path_from_url(url.removeprefix("http://card.local"))
                    if path is not None and path.is_file():
                        await route.fulfill(body=path.read_bytes(), content_type={
                            ".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp",
                            ".gif": "image/gif",
                        }.get(path.suffix.lower(), "application/octet-stream"))
                        return
                await route.abort()
            await context.route("**/*", serve_local_asset)
            page = await context.new_page()
            pngs: list[bytes] = []
            for index, card in enumerate(deck.pages):
                # Resolve relative /uploads paths against an isolated local-only origin.
                html = render_page(deck, card, index).replace(
                    "<head>", '<head><base href="http://card.local/">', 1
                )
                await page.set_content(html, wait_until="load", timeout=15000)
                if any(isinstance(block, ImageBlock) for block in card.blocks):
                    ready = await page.locator("article img").evaluate_all(
                        "images => images.every(img => img.complete && img.naturalWidth > 0)"
                    )
                    if not ready:
                        raise ValueError(f"第 {index + 1} 张卡片的图片未加载")
                overflow = await page.locator("article").evaluate(
                    "el => el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2"
                )
                if overflow:
                    raise ValueError(f"第 {index + 1} 张卡片内容溢出，请缩短文案")
                pngs.append(await page.locator("article").screenshot(type="png", timeout=15000))
            await context.close()
            return pngs
        finally:
            await browser.close()
