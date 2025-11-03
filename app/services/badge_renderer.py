from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

from ..constants import (
    BADGE_TEXT_LOCATIONS,
    DEFAULT_BADGE_FONT_SIZE,
    DEFAULT_BADGE_TEXT_LOCATION,
    DEFAULT_IMAGE_COLOR,
    DEFAULT_IMAGE_FONT,
)

FONTS_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
_LOCATION_ALIAS = {loc.lower(): loc for loc in BADGE_TEXT_LOCATIONS}


def _ensure_font_path(font_filename: str) -> Path:
    font_file = (FONTS_DIR / font_filename).resolve()
    if not font_file.is_file():
        raise FileNotFoundError(f"Font file '{font_filename}' not found in fonts directory.")
    return font_file


def _calculate_position(
    location: str,
    *,
    image_size: Tuple[int, int],
    text_size: Tuple[int, int],
    padding: int = 12,
) -> Tuple[int, int]:
    width, height = image_size
    text_width, text_height = text_size

    location_key = location.strip().lower()
    if "," in location_key:
        try:
            x_str, y_str = location_key.split(",", 1)
            return int(x_str.strip()), int(y_str.strip())
        except ValueError as exc:
            raise ValueError("Custom coordinates must be in 'x,y' format.") from exc

    location_name = _LOCATION_ALIAS.get(location_key, DEFAULT_BADGE_TEXT_LOCATION)

    if "top" in location_name:
        y = padding
    elif "bottom" in location_name:
        y = height - text_height - padding
    else:
        y = (height - text_height) // 2

    if "left" in location_name:
        x = padding
    elif "right" in location_name:
        x = width - text_width - padding
    else:
        x = (width - text_width) // 2

    return x, y


def render_badge_image(
    *,
    image_base64: str,
    attendee_name: str,
    font_filename: str = DEFAULT_IMAGE_FONT,
    font_size: int = DEFAULT_BADGE_FONT_SIZE,
    text_color: str = DEFAULT_IMAGE_COLOR,
    text_location: str = DEFAULT_BADGE_TEXT_LOCATION,
) -> str:
    image_bytes = base64.b64decode(image_base64)
    with Image.open(BytesIO(image_bytes)) as original_img:
        image_format = original_img.format or "PNG"
        img = original_img.convert("RGBA")

        try:
            font_path = _ensure_font_path(font_filename)
        except FileNotFoundError:
            if font_filename != DEFAULT_IMAGE_FONT:
                font_path = _ensure_font_path(DEFAULT_IMAGE_FONT)
            else:
                raise
        try:
            font = ImageFont.truetype(str(font_path), font_size)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Unable to load font '{font_filename}'.") from exc

        draw = ImageDraw.Draw(img)
        bbox = font.getbbox(attendee_name)
        left, top, right, bottom = bbox
        text_width = right - left
        text_height = bottom - top

        explicit_coordinates = "," in text_location.strip()
        x, y = _calculate_position(
            text_location,
            image_size=img.size,
            text_size=(text_width, text_height),
        )
        if explicit_coordinates:
            x = max(0, x)
            y = max(0, y)
        else:
            max_x = max(img.width - text_width, 0)
            max_y = max(img.height - text_height, 0)
            x = max(0, min(max_x, x))
            y = max(0, min(max_y, y))

        fill = (0, 0, 0, 255) if text_color.lower() == "black" else (255, 255, 255, 255)

        draw.text(
            (x - left, y - top),
            attendee_name,
            font=font,
            fill=fill,
        )

        output = BytesIO()
        final_image = img
        if original_img.mode != "RGBA":
            final_image = img.convert(original_img.mode)
        elif original_img.mode == "RGBA" and original_img.info.get("transparency") is not None:
            final_image = img
        final_image.save(output, format=image_format)
    return base64.b64encode(output.getvalue()).decode("ascii")
