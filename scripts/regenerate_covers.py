#!/usr/bin/env python3
"""Regenerate social cover images for legal-hallucination-bench.

Uses only stdlib + Pillow. Fonts searched in common macOS / Linux paths.
Output: docs/zhihu_cover.png (1200x675), docs/wechat_cover.png (960x408)
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Pillow is required: "
        "/Users/vickywu/.workbuddy/binaries/python/versions/3.13.12/bin/python3 -m pip install Pillow"
    ) from exc


REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "docs"

# Color palette (approximates the existing dark-cover style)
BG = "#0b1120"
TEXT_WHITE = "#f8fafc"
TEXT_GRAY = "#94a3b8"
ACCENT_RED = "#ef4444"
ACCENT_CYAN = "#2dd4bf"


def find_font(preferred: Tuple[str, ...] = ()) -> str:
    candidates = list(preferred) + [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/usr/share/fonts/truetype/arialuni.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    raise FileNotFoundError("No usable font found for CJK rendering")


def load_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(find_font(), size)


def draw_text_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: str,
    anchor: str = "lm",
) -> Tuple[int, int, int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if anchor == "lm":
        x0, y0 = x, y - h // 2
    elif anchor == "mm":
        x0, y0 = x - w // 2, y - h // 2
    elif anchor == "rm":
        x0, y0 = x - w, y - h // 2
    else:
        x0, y0 = x, y
    draw.text((x0, y0), text, font=font, fill=fill)
    return x0, y0, x0 + w, y0 + h


def generate_zhihu(path: Path) -> None:
    width, height = 1200, 675
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # Top header
    font_header = load_font(28)
    draw_text_centered(
        draw,
        "中文法律 AI 引注幻觉基准 · 离线零依赖开源评测",
        width // 2,
        70,
        font_header,
        TEXT_GRAY,
        anchor="mm",
    )

    # Main title lines
    font_title = load_font(74)
    font_zero = load_font(140)
    font_suffix = load_font(74)

    y = 160
    draw_text_centered(
        draw,
        "5 个国产法律 AI 实测：",
        80,
        y,
        font_title,
        TEXT_WHITE,
        anchor="lm",
    )
    y += 100
    draw_text_centered(
        draw,
        "增值税法 42 次引注，",
        80,
        y,
        font_title,
        TEXT_WHITE,
        anchor="lm",
    )

    # Big red 0 line
    y += 110
    zero_text = "0"
    suffix_text = " 次逐字正确"
    x_cursor = 80
    _, _, x1, _ = draw_text_centered(
        draw, zero_text, x_cursor, y, font_zero, ACCENT_RED, anchor="lm"
    )
    # underline under the zero
    underline_y = y + font_zero.size // 2 - 5
    draw.line([(x_cursor, underline_y), (x1, underline_y)], fill=ACCENT_RED, width=6)
    draw_text_centered(
        draw, suffix_text, x1 + 12, y + 10, font_suffix, TEXT_WHITE, anchor="lm"
    )

    # Stats line
    y = height - 130
    font_stats = load_font(26)
    draw_text_centered(
        draw,
        "2327 条专家核验法条 · HVI 33.3%~54.2% · 5 模型真实跑分",
        width // 2,
        y,
        font_stats,
        TEXT_GRAY,
        anchor="mm",
    )

    # Bottom URL / tagline
    font_bottom = load_font(26)
    draw_text_centered(
        draw,
        "github.com/vickywu97     legal-hallucination-bench / compliance-triangle",
        width // 2,
        y + 42,
        font_bottom,
        TEXT_GRAY,
        anchor="mm",
    )
    draw_text_centered(
        draw,
        "律师 · 税务师 · 专利代理师 ｜ 在做 AI 法律产品",
        width // 2,
        y + 84,
        load_font(28),
        ACCENT_CYAN,
        anchor="mm",
    )

    img.save(path, "PNG")


def generate_wechat(path: Path) -> None:
    width, height = 960, 408
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # Top header
    font_header = load_font(22)
    draw_text_centered(
        draw,
        "中文法律 AI 引注幻觉基准 · 离线零依赖开源评测",
        width // 2,
        46,
        font_header,
        TEXT_GRAY,
        anchor="mm",
    )

    font_title = load_font(48)
    font_zero = load_font(90)
    font_suffix = load_font(48)

    y = 96
    draw_text_centered(
        draw,
        "5 个国产法律 AI 实测：",
        60,
        y,
        font_title,
        TEXT_WHITE,
        anchor="lm",
    )
    y += 66
    draw_text_centered(
        draw,
        "增值税法 42 次引注，",
        60,
        y,
        font_title,
        TEXT_WHITE,
        anchor="lm",
    )

    y += 72
    zero_text = "0"
    suffix_text = " 次逐字正确"
    x_cursor = 60
    _, _, x1, _ = draw_text_centered(
        draw, zero_text, x_cursor, y, font_zero, ACCENT_RED, anchor="lm"
    )
    underline_y = y + font_zero.size // 2 - 4
    draw.line([(x_cursor, underline_y), (x1, underline_y)], fill=ACCENT_RED, width=5)
    draw_text_centered(
        draw, suffix_text, x1 + 10, y + 6, font_suffix, TEXT_WHITE, anchor="lm"
    )

    # Stats line
    y = height - 60
    font_stats = load_font(20)
    draw_text_centered(
        draw,
        "2327 条专家核验法条 · HVI 33.3%~54.2% · 5 模型真实跑分",
        width // 2,
        y,
        font_stats,
        TEXT_GRAY,
        anchor="mm",
    )

    draw_text_centered(
        draw,
        "github.com/vickywu97 · 律师 · 税务师 · 专利代理师 ｜ 在做 AI 法律产品",
        width // 2,
        y + 30,
        load_font(20),
        ACCENT_CYAN,
        anchor="mm",
    )

    img.save(path, "PNG")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generate_zhihu(OUT_DIR / "zhihu_cover.png")
    generate_wechat(OUT_DIR / "wechat_cover.png")
    print(f"Covers regenerated:\n  {OUT_DIR / 'zhihu_cover.png'}\n  {OUT_DIR / 'wechat_cover.png'}")
