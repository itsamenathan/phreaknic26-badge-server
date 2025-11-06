from __future__ import annotations

import base64
import binascii
from pathlib import Path
from typing import Optional, Tuple

from .patch_firmware_image import (
    convert_png_bytes_to_pixel_data,
    patch_firmware_bytes,
)

TARGET_WIDTH = 240
TARGET_HEIGHT = 96

DEFAULT_FIRMWARE_PATH = (
    Path(__file__).resolve().parent.parent / "static" / "firmware" / "default.bin"
)


class FirmwareGenerationError(RuntimeError):
    """Raised when firmware could not be generated."""


def _load_firmware(firmware_path: Optional[Path]) -> bytes:
    path = firmware_path or DEFAULT_FIRMWARE_PATH
    try:
        data = Path(path).read_bytes()
    except FileNotFoundError as exc:
        raise FirmwareGenerationError(
            f"Firmware image not found at {path}."
        ) from exc
    except OSError as exc:  # pragma: no cover - IO error
        raise FirmwareGenerationError(f"Unable to read firmware image at {path}.") from exc
    return data


def generate_firmware_from_image(
    image_base64: str,
    *,
    firmware_path: Optional[Path] = None,
) -> Tuple[bytes, str]:
    """Generate a firmware blob by patching the default binary with the rendered badge image."""
    try:
        image_bytes = base64.b64decode(image_base64)
    except (ValueError, binascii.Error) as exc:  # pragma: no cover - invalid input guard
        raise FirmwareGenerationError("Rendered image payload is not valid base64.") from exc

    try:
        pixel_bytes, width, height = convert_png_bytes_to_pixel_data(
            image_bytes,
            target_width=TARGET_WIDTH,
            target_height=TARGET_HEIGHT,
        )
    except Exception as exc:  # pragma: no cover - PIL-related errors
        raise FirmwareGenerationError("Unable to process rendered badge image.") from exc

    if (width, height) != (TARGET_WIDTH, TARGET_HEIGHT):
        raise FirmwareGenerationError(
            f"Rendered image must be {TARGET_WIDTH}x{TARGET_HEIGHT} pixels; got {width}x{height}."
        )

    firmware_bytes = _load_firmware(firmware_path)
    try:
        patched_bytes, _, _, hash_bytes, _, _ = patch_firmware_bytes(firmware_bytes, pixel_bytes)
    except RuntimeError as exc:
        raise FirmwareGenerationError(str(exc)) from exc

    firmware_hash = hash_bytes.hex().upper()
    return patched_bytes, firmware_hash
