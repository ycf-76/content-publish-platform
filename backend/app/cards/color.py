"""Color token utilities for the structured-card theme system.

The old ``THEMES`` hardcoded six hex values per theme (bg/surface/text/muted/
accent/line). That made ``surface`` nearly identical to ``bg`` (measured
``bg↔surface`` ≈ 1.05–1.29 for every theme), so bento/compare panels were
beige-on-beige and the nine themes looked like one beige.

The fix: each theme only declares a *base* (``bg`` / ``text`` / ``accent``) plus a
*style* (font / weight / radius / character). ``surface`` / ``line`` / ``muted``
are **derived** from ``bg`` and ``text`` with HSL lightness shifts / blends, and
**verified against WCAG contrast floors** so every theme gets real panel
separation and readable secondary text. Adding a theme is now "pick a base +
style", not "hand-tune six hex that accidentally collide".

Accent is a deliberate brand/design choice, so it stays explicit in ``THEMES``;
:func:`accessible_accent` only nudges it (preserving hue) when it would otherwise
fall below the UI contrast floor.
"""

from __future__ import annotations

import colorsys

# A theme is "dark" when its background is darker than this relative luminance.
_DARK_LUM_THRESHOLD = 0.40
# Required contrast floors (WCAG 2.1).
_SURFACE_MIN = 1.6       # panel vs page must be visibly separated
_LINE_MIN = 1.9          # hairline / divider, more separated than surface
_MUTED_AA = 4.5          # secondary text vs page (normal-size AA)
_ACCENT_UI = 3.0         # accent is used for small UI bits (kickers, tags)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, int(round(c)))):02x}" for c in rgb)


def _linear(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    r, g, b = hex_to_rgb(hex_color)
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast(a: str, b: str) -> float:
    l1, l2 = relative_luminance(a), relative_luminance(b)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def rgb_blend(a: str, b: str, t: float) -> str:
    """Linear interpolation between two hex colors (t=0 → a, t=1 → b)."""
    ra, ga, ba = hex_to_rgb(a)
    rb, gb, bb = hex_to_rgb(b)
    return rgb_to_hex((ra + (rb - ra) * t, ga + (gb - ga) * t, ba + (bb - ba) * t))


def shift_lightness(hex_color: str, delta: float) -> str:
    """Shift lightness in HLS space. Positive lightens, negative darkens."""
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in hex_to_rgb(hex_color)))
    l = max(0.0, min(1.0, l + delta))
    return rgb_to_hex(tuple(round(c * 255) for c in colorsys.hls_to_rgb(h, l, s)))


def derive_tokens(bg: str, text: str, accent: str) -> dict[str, str]:
    """Derive surface/line/muted from bg+text, **enforcing** WCAG contrast floors.

    Returns a dict of CSS variable values (without the leading ``--``). Every
    returned value is guaranteed to meet its floor: ``bg↔surface ≥ _SURFACE_MIN``,
    ``bg↔line ≥ _LINE_MIN``, ``bg↔muted ≥ _MUTED_AA``.
    """
    is_dark = relative_luminance(bg) < _DARK_LUM_THRESHOLD
    # Light themes push panels darker; dark themes push them lighter.
    sign = -1.0 if not is_dark else 1.0

    # surface: a panel background clearly distinct from the page.
    mag = 0.16
    surface = shift_lightness(bg, sign * mag)
    while contrast(bg, surface) < _SURFACE_MIN and mag < 0.6:
        mag += 0.02
        surface = shift_lightness(bg, sign * mag)

    # line: a hairline / divider, more separated than surface.
    mag = 0.32
    line = shift_lightness(bg, sign * mag)
    while contrast(bg, line) < _LINE_MIN and mag < 0.75:
        mag += 0.02
        line = shift_lightness(bg, sign * mag)

    # muted: secondary text. Blend bg→text until it clears AA normal contrast.
    # If the theme's text color is itself too light/dark to ever clear AA (e.g.
    # a soft-cream theme), fall back to blending toward the contrasting pole so
    # secondary text stays readable no matter what.
    t = 0.60
    while t <= 0.86:
        candidate = rgb_blend(bg, text, t)
        if contrast(bg, candidate) >= _MUTED_AA:
            break
        t += 0.03
    muted = rgb_blend(bg, text, t)
    if contrast(bg, muted) < _MUTED_AA:
        pole = "#000000" if not is_dark else "#ffffff"
        u = 0.42
        while u <= 0.78:
            candidate = rgb_blend(bg, pole, u)
            if contrast(bg, candidate) >= _MUTED_AA:
                break
            u += 0.03
        muted = rgb_blend(bg, pole, u)

    # Accent: only nudge if it falls below the UI floor; preserves hue.
    accent = accessible_accent(bg, accent)

    return {"surface": surface, "line": line, "muted": muted, "accent": accent}


def accessible_accent(bg: str, accent: str) -> str:
    """Return ``accent`` unchanged if it clears the UI floor, else a deeper/lighter
    shade of the same hue that does. Keeps the designer's hue, only adjusts
    lightness until ``bg↔accent ≥ _ACCENT_UI``.
    """
    if contrast(bg, accent) >= _ACCENT_UI:
        return accent
    is_dark = relative_luminance(bg) < _DARK_LUM_THRESHOLD
    # On light bg, deepen the accent; on dark bg, lighten it.
    delta = -0.04 if not is_dark else 0.04
    cur = accent
    steps = 0
    while contrast(bg, cur) < _ACCENT_UI and steps < 25:
        cur = shift_lightness(cur, delta)
        steps += 1
    # Hard floor: if hue-shifting alone can't reach it (rare), snap to a safe pole.
    if contrast(bg, cur) < _ACCENT_UI:
        cur = "#1a1a1a" if not is_dark else "#ffffff"
    return cur


def accent_contrast_ok(bg: str, accent: str) -> bool:
    """Accent is used for small UI bits (kickers, tags); ≥3.0 is the UI floor."""
    return contrast(bg, accent) >= _ACCENT_UI


if __name__ == "__main__":  # pragma: no cover - manual audit helper
    from app.cards.schema import THEMES

    print(f"{'theme':10} {'mode':5} {'bg↔surface':>11} {'bg↔muted':>10} {'bg↔accent':>11}  derived tokens")
    print("-" * 78)
    for tid, spec in THEMES.items():
        toks = derive_tokens(spec["bg"], spec["text"], spec["accent"])
        print(
            f"{tid:10} {'dark' if relative_luminance(spec['bg']) < _DARK_LUM_THRESHOLD else 'light':5} "
            f"{contrast(spec['bg'], toks['surface']):>11.2f} "
            f"{contrast(spec['bg'], toks['muted']):>10.2f} "
            f"{contrast(spec['bg'], toks['accent']):>11.2f}  "
            f"surface={toks['surface']} line={toks['line']} muted={toks['muted']} accent={toks['accent']}"
        )
