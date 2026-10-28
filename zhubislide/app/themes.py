"""Design themes shared by the PPTX builder and the web preview (served as JSON)."""

from __future__ import annotations

import re

THEMES: dict[str, dict] = {
    "aurora": {
        "name": {"kk": "Аврора", "ru": "Аврора"},
        "dark": True,
        "bg": ["0B0B23", "2A0E4F"], "angle": 135,
        "surface": "1C1745", "text": "FFFFFF", "muted": "B9B4E0",
        "accent": "8B5CF6", "accent2": "22D3EE",
    },
    "ocean": {
        "name": {"kk": "Мұхит", "ru": "Океан"},
        "dark": True,
        "bg": ["021B33", "053B5E"], "angle": 120,
        "surface": "0A2F4D", "text": "FFFFFF", "muted": "A7C7E0",
        "accent": "06B6D4", "accent2": "3B82F6",
    },
    "sunset": {
        "name": {"kk": "Шұғыла", "ru": "Закат"},
        "dark": True,
        "bg": ["2B0B1E", "5C1A2E"], "angle": 135,
        "surface": "45142C", "text": "FFFFFF", "muted": "F3C2C8",
        "accent": "FB7185", "accent2": "F59E0B",
    },
    "emerald": {
        "name": {"kk": "Зүбәржат", "ru": "Изумруд"},
        "dark": True,
        "bg": ["03201A", "064E3B"], "angle": 135,
        "surface": "0B3A2F", "text": "FFFFFF", "muted": "A7E3CC",
        "accent": "10B981", "accent2": "A3E635",
    },
    "noir": {
        "name": {"kk": "Нуар Голд", "ru": "Нуар Голд"},
        "dark": True,
        "bg": ["0A0A0A", "1F1A12"], "angle": 160,
        "surface": "1E1E1E", "text": "FFFFFF", "muted": "C9BFA8",
        "accent": "D4AF37", "accent2": "F5E6B3",
    },
    "minimal": {
        "name": {"kk": "Минимал", "ru": "Минимал"},
        "dark": False,
        "bg": ["FFFFFF", "EEF2FF"], "angle": 135,
        "surface": "F1F5F9", "text": "0F172A", "muted": "475569",
        "accent": "4F46E5", "accent2": "0EA5E9",
    },
    "steppe": {
        "name": {"kk": "Дала", "ru": "Степь"},
        "dark": False,
        "bg": ["FFF8EB", "FDE7C2"], "angle": 135,
        "surface": "FFFFFF", "text": "3B2410", "muted": "7C5A3A",
        "accent": "0EA5E9", "accent2": "EAB308",
    },
}

DEFAULT_THEME = "aurora"

# Fonts installed with Windows/macOS/Office that cover every Kazakh letter (ә ғ қ ң ө ұ ү һ і).
# char_w: average glyph width in em, used to fit long text into boxes; css: stack for the web preview.
FONTS: dict[str, dict] = {
    "Arial": {"char_w": 0.54, "css": "Arial, 'Helvetica Neue', Helvetica, sans-serif"},
    "Times New Roman": {"char_w": 0.47, "css": "'Times New Roman', Times, 'Liberation Serif', serif"},
    "Calibri": {"char_w": 0.49, "css": "Calibri, Carlito, 'Segoe UI', sans-serif"},
    "Cambria": {"char_w": 0.52, "css": "Cambria, Caladea, Georgia, serif"},
    "Segoe UI": {"char_w": 0.54, "css": "'Segoe UI', system-ui, -apple-system, sans-serif"},
    "Verdana": {"char_w": 0.62, "css": "Verdana, 'DejaVu Sans', sans-serif"},
    "Tahoma": {"char_w": 0.53, "css": "Tahoma, Verdana, sans-serif"},
    "Courier New": {"char_w": 0.61, "css": "'Courier New', Courier, monospace"},
}

AUTO = "auto"
PATTERNS = ["blobs", "geometric", "lines", "dots"]
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _hex(v: str, fallback: str) -> str:
    m = _HEX.match((v or "").strip())
    return m.group(1).upper() if m else fallback


def _rgb(h: str) -> tuple[float, float, float]:
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _to_hex(c) -> str:
    return "".join(f"{max(0, min(255, round(x * 255))):02X}" for x in c)


def luminance(h: str) -> float:
    def ch(x):
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(x) for x in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def mix(a: str, b: str, t: float) -> str:
    return _to_hex(x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b)))


def _readable(color: str, bg: str, dark: bool, need: float = 3.0) -> str:
    """Pull the accent towards white/black until it stands out on the background."""
    target = "FFFFFF" if dark else "000000"
    for step in range(11):
        c = mix(color, target, step * 0.08)
        if contrast(c, bg) >= need:
            return c
    return target


def from_design(d: dict) -> dict:
    """Theme from the palette Claude picked for the topic, corrected so text is always readable."""
    dark = bool(d.get("dark", True))
    bg1 = _hex(d.get("bg1"), "0B0B23" if dark else "FFFFFF")
    bg2 = _hex(d.get("bg2"), bg1)
    # dark themes must really be dark, light ones really light (white/black text on them)
    for _ in range(12):
        lum = max(luminance(bg1), luminance(bg2))
        if dark and lum > 0.06:
            bg1, bg2 = mix(bg1, "000000", 0.2), mix(bg2, "000000", 0.2)
        elif not dark and min(luminance(bg1), luminance(bg2)) < 0.75:
            bg1, bg2 = mix(bg1, "FFFFFF", 0.25), mix(bg2, "FFFFFF", 0.25)
        else:
            break
    mid = mix(bg1, bg2, 0.5)
    text = "FFFFFF" if dark else "111827"
    accent = _readable(_hex(d.get("accent"), "8B5CF6"), mid, dark)
    accent2 = _readable(_hex(d.get("accent2"), "22D3EE"), mid, dark)
    return {
        "name": {"kk": "Авто", "ru": "Авто"},
        "dark": dark,
        "bg": [bg1, bg2], "angle": 135,
        "surface": mix(mid, "FFFFFF" if dark else accent, 0.08 if dark else 0.06),
        "text": text, "muted": mix(text, mid, 0.35),
        "accent": accent, "accent2": accent2,
        "pattern": d.get("pattern") if d.get("pattern") in PATTERNS else "blobs",
    }


def resolve(name: str, deck: dict | None) -> dict:
    if name == AUTO and deck and isinstance(deck.get("design"), dict):
        return from_design(deck["design"])
    return THEMES.get(name) or THEMES[DEFAULT_THEME]
