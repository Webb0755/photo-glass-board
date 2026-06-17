#!/usr/bin/env python3
"""
Create a reference-style photo board: the photo is repeated as a blurred,
darkened background board, while the sharp photo floats above it with a
minimal presentation caption.

Example:
    python3 photo_glass_board.py input.jpg -o output.jpg --location "Shanghai"

Dependencies:
    python3 -m pip install pillow
"""

from __future__ import annotations

import argparse
import math
import os
from fractions import Fraction
from pathlib import Path
from typing import Any

try:
    from PIL import ExifTags, Image, ImageDraw, ImageFilter, ImageFont, ImageOps
except ModuleNotFoundError:
    ExifTags = Image = ImageDraw = ImageFilter = ImageFont = ImageOps = None


CM_PER_INCH = 2.54
DEFAULT_DPI = 300


def ensure_pillow() -> None:
    if Image is None:
        raise SystemExit(
            "Missing dependency: Pillow. Install it with:\n"
            "  python3 -m pip install -r requirements-photo-board.txt"
        )


def cm_to_px(cm: float, dpi: int) -> int:
    return max(1, round(cm / CM_PER_INCH * dpi))


def ratio_to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Fraction):
        return float(value)
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        return float(value.numerator) / float(value.denominator)
    if isinstance(value, tuple) and len(value) == 2 and value[1]:
        return float(value[0]) / float(value[1])
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_shutter(value: Any) -> str | None:
    seconds = ratio_to_float(value)
    if not seconds or seconds <= 0:
        return None
    if seconds < 1:
        denominator = round(1 / seconds)
        return f"1/{denominator}s"
    if abs(seconds - round(seconds)) < 0.01:
        return f"{round(seconds)}s"
    return f"{seconds:.1f}s"


def format_focal_length(value: Any) -> str | None:
    focal = ratio_to_float(value)
    if focal is None:
        return None
    if abs(focal - round(focal)) < 0.05:
        return f"{round(focal)}mm"
    return f"{focal:.1f}mm"


def format_aperture(value: Any) -> str | None:
    aperture = ratio_to_float(value)
    if aperture is None or aperture <= 0:
        return None
    if abs(aperture - round(aperture)) < 0.05:
        return f"f/{round(aperture)}"
    return f"f/{aperture:.1f}"


def gps_to_decimal(value: Any, ref: str | None) -> float | None:
    if not value or len(value) != 3:
        return None
    degrees = ratio_to_float(value[0])
    minutes = ratio_to_float(value[1])
    seconds = ratio_to_float(value[2])
    if degrees is None or minutes is None or seconds is None:
        return None
    decimal = degrees + minutes / 60 + seconds / 3600
    if ref in {"S", "W"}:
        decimal *= -1
    return decimal


def read_exif(image: Image.Image) -> dict[str, Any]:
    raw = image.getexif()
    if not raw:
        return {}

    decoded: dict[str, Any] = {}
    for tag_id, value in raw.items():
        tag = ExifTags.TAGS.get(tag_id, tag_id)
        decoded[str(tag)] = value

    exif_ifd = raw.get_ifd(ExifTags.IFD.Exif) if hasattr(raw, "get_ifd") else {}
    for tag_id, value in exif_ifd.items():
        tag = ExifTags.TAGS.get(tag_id, tag_id)
        decoded[str(tag)] = value

    gps_ifd = raw.get_ifd(ExifTags.IFD.GPSInfo) if hasattr(raw, "get_ifd") else {}
    if gps_ifd:
        gps = {
            str(ExifTags.GPSTAGS.get(tag_id, tag_id)): value
            for tag_id, value in gps_ifd.items()
        }
        lat = gps_to_decimal(gps.get("GPSLatitude"), gps.get("GPSLatitudeRef"))
        lon = gps_to_decimal(gps.get("GPSLongitude"), gps.get("GPSLongitudeRef"))
        if lat is not None and lon is not None:
            decoded["GPSDecimal"] = f"{lat:.5f}, {lon:.5f}"

    return decoded


def find_font(size: int, italic: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/Library/Fonts/Times New Roman Italic.ttf",
        "/Library/Fonts/Times New Roman.ttf",
        "/System/Library/Fonts/Times.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ]

    if not italic:
        candidates = [path for path in candidates if "Italic" not in path] + candidates

    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    if not text:
        return (0, 0)
    bbox = draw.textbbox((0, 0), text, font=font)
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])


def fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
    min_size: int = 14,
    italic: bool = False,
) -> ImageFont.ImageFont:
    for size in range(start_size, min_size - 1, -1):
        font = find_font(size, italic=italic)
        width, _ = text_size(draw, text, font)
        if width <= max_width:
            return font
    return find_font(min_size, italic=italic)


def cover_resize(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    src_w, src_h = image.size
    scale = max(target_w / src_w, target_h / src_h)
    resized = image.resize((math.ceil(src_w * scale), math.ceil(src_h * scale)), Image.Resampling.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def letter_spaced(text: str, gap: str = " ") -> str:
    compact = text.strip().upper()
    return gap.join(char for char in compact if char != " ")


def draw_bottom_gradient(canvas: Image.Image, start_y: int) -> None:
    width, height = canvas.size
    gradient = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    pixels = gradient.load()
    for y in range(start_y, height):
        t = (y - start_y) / max(1, height - start_y)
        alpha = int(205 * min(1.0, t**0.72))
        for x in range(width):
            pixels[x, y] = (0, 7, 24, alpha)
    canvas.alpha_composite(gradient)


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return mask


def paste_shadow(
    canvas: Image.Image,
    box: tuple[int, int, int, int],
    radius: int,
    blur: int,
    offset_y: int,
    opacity: int,
) -> None:
    x0, y0, x1, y1 = box
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    mask = rounded_mask((x1 - x0, y1 - y0), radius)
    shadow_shape = Image.new("RGBA", mask.size, (0, 0, 0, opacity))
    shadow.alpha_composite(shadow_shape, (x0, y0 + offset_y))
    shadow.putalpha(shadow.getchannel("A").filter(ImageFilter.GaussianBlur(blur)))
    canvas.alpha_composite(shadow)


def apply_glass_finish(photo: Image.Image, radius: int) -> Image.Image:
    photo = photo.convert("RGBA")
    width, height = photo.size
    mask = rounded_mask(photo.size, radius)

    finished = Image.new("RGBA", photo.size, (0, 0, 0, 0))
    finished.alpha_composite(photo)
    finished.putalpha(mask)

    sheen = Image.new("RGBA", photo.size, (255, 255, 255, 0))
    sheen_pixels = sheen.load()
    for y in range(height):
        vertical = max(0.0, 1.0 - y / max(1, height * 0.65))
        for x in range(width):
            diagonal = max(0.0, 1.0 - (x / max(1, width) * 0.55 + y / max(1, height)))
            alpha = int(55 * vertical * diagonal)
            sheen_pixels[x, y] = (255, 255, 255, alpha)
    sheen.putalpha(Image.composite(sheen.getchannel("A"), Image.new("L", photo.size, 0), mask))
    finished.alpha_composite(sheen)

    draw = ImageDraw.Draw(finished)
    inset = max(1, round(radius * 0.08))
    draw.rounded_rectangle(
        (inset, inset, width - inset - 1, height - inset - 1),
        radius=max(1, radius - inset),
        outline=(255, 255, 255, 115),
        width=max(1, round(width * 0.003)),
    )
    draw.rounded_rectangle(
        (0, 0, width - 1, height - 1),
        radius=radius,
        outline=(0, 0, 0, 36),
        width=max(1, round(width * 0.002)),
    )
    return finished


def build_camera_line(exif: dict[str, Any], override: str | None) -> str:
    if override:
        return override
    make = str(exif.get("Make", "")).strip()
    model = str(exif.get("Model", "")).strip()
    if make and model and not model.lower().startswith(make.lower()):
        return f"{make} {model}"
    return model or make


def build_brand_line(exif: dict[str, Any], override: str | None) -> str:
    if override:
        return letter_spaced(override)
    make = str(exif.get("Make", "")).strip()
    model = str(exif.get("Model", "")).strip()
    brand = make or model
    return letter_spaced(brand) if brand else ""


def format_iso(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text if text.upper().startswith("ISO") else f"ISO{text}"


def build_exposure_line(exif: dict[str, Any], args: argparse.Namespace) -> str:
    focal = args.focal_length or format_focal_length(exif.get("FocalLength"))
    aperture = args.aperture or format_aperture(exif.get("FNumber"))
    shutter = args.shutter or format_shutter(exif.get("ExposureTime"))
    iso = format_iso(args.iso or exif.get("ISOSpeedRatings") or exif.get("PhotographicSensitivity"))
    location = args.location or exif.get("GPSDecimal")
    date = args.date or exif.get("DateTimeOriginal") or exif.get("DateTime")
    if date:
        date = str(date).replace(":", "-", 2)

    parts = [focal, aperture, shutter, iso, location, date, *args.extra_info]
    return "    ".join(str(part) for part in parts if part)


def render(args: argparse.Namespace) -> None:
    ensure_pillow()

    input_path = Path(args.input).expanduser()
    output_path = Path(args.output or input_path.with_name(f"{input_path.stem}_board.jpg"))

    with Image.open(input_path) as opened:
        photo = ImageOps.exif_transpose(opened).convert("RGB")
        exif = read_exif(opened)

    photo_w, photo_h = photo.size
    side_margin = round(photo_w * args.side_margin_ratio)
    top_margin = round(photo_h * args.top_margin_ratio)
    bottom_margin = round(photo_h * args.bottom_margin_ratio)
    canvas_w = photo_w + side_margin * 2
    canvas_h = photo_h + top_margin + bottom_margin

    background = cover_resize(photo, (canvas_w, canvas_h)).convert("RGBA")
    background = background.filter(ImageFilter.GaussianBlur(args.background_blur))
    background = Image.blend(
        background,
        Image.new("RGBA", background.size, (11, 18, 31, 255)),
        args.background_dim,
    )
    canvas = background
    draw_bottom_gradient(canvas, round(canvas_h * 0.50))

    x = side_margin
    y = top_margin
    radius = max(0, round(min(photo_w, photo_h) * args.corner_radius_ratio))
    blur = max(16, round(min(photo_w, photo_h) * 0.035))
    shadow_offset = max(6, round(blur * 0.20))

    paste_shadow(
        canvas,
        (x, y, x + photo_w, y + photo_h),
        radius=radius,
        blur=blur,
        offset_y=shadow_offset,
        opacity=args.shadow_opacity,
    )

    sharp_photo = photo.convert("RGBA")
    if radius:
        mask = rounded_mask(sharp_photo.size, radius)
        sharp_photo.putalpha(mask)
    canvas.alpha_composite(sharp_photo, (x, y))

    border = ImageDraw.Draw(canvas)
    border.rectangle(
        (x, y, x + photo_w - 1, y + photo_h - 1),
        outline=(255, 255, 255, args.photo_border_opacity),
        width=max(1, round(photo_w * 0.0012)),
    )

    draw = ImageDraw.Draw(canvas)
    brand = build_brand_line(exif, args.brand)
    metadata = args.caption or build_exposure_line(exif, args)
    camera = build_camera_line(exif, args.camera)

    caption_area_y = y + photo_h
    caption_area_h = canvas_h - caption_area_y
    brand_font_size = max(18, round(bottom_margin * 0.135))
    detail_font_size = max(18, round(bottom_margin * 0.125))
    brand_font = fit_font(
        draw,
        brand,
        max_width=round(canvas_w * 0.42),
        start_size=brand_font_size,
        min_size=14,
        italic=True,
    )
    caption_font = fit_font(
        draw,
        metadata,
        max_width=round(canvas_w * 0.58),
        start_size=detail_font_size,
        min_size=13,
        italic=True,
    )
    camera_font = fit_font(
        draw,
        camera,
        max_width=round(canvas_w * 0.24),
        start_size=round(detail_font_size * 1.02),
        min_size=13,
        italic=True,
    )

    text_color = (255, 255, 255, 238)
    brand_y = caption_area_y + round(caption_area_h * 0.30)
    detail_y = caption_area_y + round(caption_area_h * 0.58)

    if brand:
        tw, th = text_size(draw, brand, brand_font)
        draw.text(((canvas_w - tw) // 2, brand_y), brand, font=brand_font, fill=text_color)

    if metadata:
        tw, th = text_size(draw, metadata, caption_font)
        tx = (canvas_w - tw) // 2
        draw.text((tx, detail_y), metadata, font=caption_font, fill=text_color)

    if camera:
        tw, th = text_size(draw, camera, camera_font)
        tx = canvas_w - side_margin - tw
        draw.text((tx, detail_y), camera, font=camera_font, fill=(255, 255, 255, 230))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    save_image = canvas.convert("RGB")
    save_kwargs: dict[str, Any] = {"quality": args.quality}
    if output_path.suffix.lower() in {".jpg", ".jpeg"}:
        save_kwargs["subsampling"] = 0
    save_image.save(output_path, **save_kwargs)
    print(f"Saved: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a blurred-background presentation board with a floating photo."
    )
    parser.add_argument("input", help="Input photo path.")
    parser.add_argument("-o", "--output", help="Output image path. Defaults to *_board.jpg.")
    parser.add_argument(
        "--side-margin-ratio",
        type=float,
        default=0.05,
        help="Left/right margin as a ratio of the photo width.",
    )
    parser.add_argument(
        "--top-margin-ratio",
        type=float,
        default=0.10,
        help="Top margin as a ratio of the photo height.",
    )
    parser.add_argument(
        "--bottom-margin-ratio",
        type=float,
        default=0.20,
        help="Bottom caption-board height as a ratio of the photo height.",
    )
    parser.add_argument("--background-blur", type=float, default=58, help="Blur radius for the board background.")
    parser.add_argument("--background-dim", type=float, default=0.30, help="Darkening blend for the board background.")
    parser.add_argument("--location", help="Location text. Uses GPS coordinates from EXIF when omitted.")
    parser.add_argument("--date", help="Date text override.")
    parser.add_argument("--focal-length", help="Focal length text override, e.g. 50mm.")
    parser.add_argument("--aperture", help="Aperture text override, e.g. f/2.0.")
    parser.add_argument("--iso", help="ISO text override, e.g. 100.")
    parser.add_argument("--shutter", help="Shutter speed text override, e.g. 1/250s.")
    parser.add_argument("--caption", help="Full centered caption override.")
    parser.add_argument(
        "--extra-info",
        action="append",
        default=[],
        help="Extra manually entered caption field. Can be passed multiple times.",
    )
    parser.add_argument("--brand", help="Centered brand line override, e.g. Hasselblad.")
    parser.add_argument("--camera", help="Camera model override.")
    parser.add_argument("--quality", type=int, default=95, help="JPEG/WebP output quality.")
    parser.add_argument(
        "--corner-radius-ratio",
        type=float,
        default=0.0,
        help="Rounded photo corner radius as a ratio of the shorter side.",
    )
    parser.add_argument("--photo-border-opacity", type=int, default=28, help="Subtle photo border alpha, 0-255.")
    parser.add_argument("--shadow-opacity", type=int, default=120, help="Shadow alpha, 0-255.")
    return parser.parse_args()


def main() -> None:
    render(parse_args())


if __name__ == "__main__":
    main()
