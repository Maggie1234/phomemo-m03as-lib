"""
图像处理工具
============
PIL Image / 文字  →  热敏打印机 1bpp ESC/POS 位图
"""
from __future__ import annotations

import os
from PIL import Image, ImageDraw, ImageFont
import numpy as np


_FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhbd.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "C:/Windows/Fonts/simkai.ttf",
    "C:/Windows/Fonts/simsun.ttc",
    # Linux / Home Assistant
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def find_chinese_font() -> str | None:
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def load_font(font_size: int, font_path: str | None = None) -> ImageFont.FreeTypeFont:
    if font_path and os.path.exists(font_path):
        return ImageFont.truetype(font_path, font_size)
    auto = find_chinese_font()
    if auto:
        return ImageFont.truetype(auto, font_size)
    return ImageFont.load_default()


def image_to_bitmap(
    img: Image.Image,
    width_px: int,
    dither: bool = True,
) -> tuple[bytes, int, int]:
    """
    PIL Image → 1bpp ESC/POS 位图字节。

    Returns:
        (bitmap_bytes, width_bytes, height_lines)
    """
    width_px = (width_px // 8) * 8
    orig_w, orig_h = img.size
    new_h = max(1, round(orig_h * width_px / orig_w))
    img = img.resize((width_px, new_h), Image.LANCZOS)

    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    img = img.convert("L")

    # Gamma 校正（参考 phomymo canvas.js，gamma=1.3，提升热敏打印中间调细节）
    arr_f = np.asarray(img, dtype=np.float32)
    arr_f = 255.0 * np.power(arr_f / 255.0, 1.0 / 1.3)
    img = Image.fromarray(arr_f.astype(np.uint8))

    if dither:
        img_1bit = img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    else:
        img_1bit = img.convert("1", dither=Image.Dither.NONE)

    arr = np.asarray(img_1bit, dtype=np.uint8)
    height = arr.shape[0]
    width_bytes = width_px // 8
    arr_print = (arr == 0).astype(np.uint8)
    bitmap = np.packbits(arr_print, axis=1, bitorder="big")
    return bitmap.tobytes(), width_bytes, height


def text_to_image(
    text: str,
    width_px: int,
    font_size: int = 40,
    font_path: str | None = None,
    padding: int = 8,
    line_spacing: int = 6,
) -> Image.Image:
    """文字 → 白底黑字 PIL Image（自动换行，支持中英混排）"""
    font = load_font(font_size, font_path)
    usable_w = width_px - 2 * padding
    input_lines = text.split("\n")
    wrapped_lines: list[str] = []
    _tmp = Image.new("L", (1, 1))
    _draw = ImageDraw.Draw(_tmp)

    for line in input_lines:
        if not line:
            wrapped_lines.append("")
            continue
        current = ""
        for char in line:
            candidate = current + char
            bbox = _draw.textbbox((0, 0), candidate, font=font)
            if bbox[2] - bbox[0] > usable_w and current:
                wrapped_lines.append(current)
                current = char
            else:
                current = candidate
        if current:
            wrapped_lines.append(current)

    sample_bbox = _draw.textbbox((0, 0), "测Ag", font=font)
    line_h = sample_bbox[3] - sample_bbox[1]
    total_h = padding + len(wrapped_lines) * (line_h + line_spacing) + padding

    img = Image.new("L", (width_px, total_h), color=255)
    draw = ImageDraw.Draw(img)
    y = padding
    for line in wrapped_lines:
        if line:
            draw.text((padding, y), line, fill=0, font=font)
        y += line_h + line_spacing
    return img


def bitmap_preview(bitmap: bytes, width_bytes: int, height_lines: int, scale: int = 2) -> None:
    """终端 ASCII 缩略图，用于快速验证位图内容"""
    chars = " ░▒▓█"
    print(f"─── 位图预览 ({width_bytes * 8}×{height_lines}px) ───")
    for row in range(0, height_lines, scale):
        line = ""
        for col_byte in range(0, width_bytes, max(1, width_bytes // 60)):
            byte = bitmap[row * width_bytes + col_byte]
            line += chars[min(4, bin(byte).count("1") // 2)]
        print(f"  |{line}|")
    print("─" * 40)
