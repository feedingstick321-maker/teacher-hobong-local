"""합성 직인/원본대조필 렌더링."""
from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont


def draw_seal(img: Image.Image, center: tuple[int, int], font_path: str, label: str = "학교장인") -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    x, y = center
    r = 64
    draw.ellipse((x-r, y-r, x+r, y+r), outline=(170, 20, 20, 210), width=7)
    font = ImageFont.truetype(font_path, 25)
    box = draw.textbbox((0, 0), label, font=font)
    draw.text((x-(box[2]-box[0])/2, y-(box[3]-box[1])/2), label, font=font, fill=(170, 20, 20, 205))


def draw_original_stamp(img: Image.Image, xy: tuple[int, int], font_path: str, angle: float = 0) -> None:
    layer = Image.new("RGBA", (300, 100), (255, 255, 255, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle((5, 5, 295, 95), outline=(30, 30, 30, 150), width=4)
    d.text((48, 25), "원 본 대 조 필", font=ImageFont.truetype(font_path, 34), fill=(20, 20, 20, 160))
    layer = layer.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC)
    img.paste(layer, xy, layer)
