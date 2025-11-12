from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .constants import DEFAULT_IMAGE_FONT, FONT_FILE_EXTENSIONS

_MAC_CLEAN_RE = re.compile(r"[^0-9A-Fa-f]")
_EXPECTED_MAC_BYTES = 8
_EXPECTED_MAC_HEX_LENGTH = _EXPECTED_MAC_BYTES * 2
_MAX_MAC_INT = (1 << (_EXPECTED_MAC_BYTES * 8)) - 1
_FONTS_DIR = (Path(__file__).resolve().parent / "static" / "fonts").resolve()

logger = logging.getLogger(__name__)


def _bytes_to_hex(mac_bytes: bytes) -> str:
    return mac_bytes.hex().upper()


def normalise_mac_address(value: Union[str, bytes, bytearray, int]) -> Optional[str]:
    """
    Return MAC address in AA:BB:CC:DD:EE:FF:00:111 format or None if invalid.

    Accepted inputs:
      * Strings in any common separator style (AA:BB:..., AA-BB-..., AABBCC..., etc.)
      * Eight-byte `bytes` / `bytearray` objects
      * Integers in the range [0, 0xFFFFFFFFFFFFFFFF]
    """
    if value is None:
        return None

    if isinstance(value, (bytes, bytearray)):
        if len(value) != _EXPECTED_MAC_BYTES:
            # Allow leading-zero-padded values by trimming zero-only prefixes.
            if len(value) > _EXPECTED_MAC_BYTES and all(
                b == 0 for b in value[:-_EXPECTED_MAC_BYTES]
            ):
                value = value[-_EXPECTED_MAC_BYTES:]
            else:
                return None
        cleaned = _bytes_to_hex(value)
    elif isinstance(value, int):
        if value < 0 or value > _MAX_MAC_INT:
            return None
        cleaned = f"{value:0{_EXPECTED_MAC_HEX_LENGTH}X}"
    else:
        text = str(value).strip()
        if not text:
            return None
        cleaned = _MAC_CLEAN_RE.sub("", text).upper()

    if len(cleaned) > _EXPECTED_MAC_HEX_LENGTH:
        prefix = cleaned[: len(cleaned) - _EXPECTED_MAC_HEX_LENGTH]
        suffix = cleaned[-_EXPECTED_MAC_HEX_LENGTH:]
        if not prefix or all(ch == "0" for ch in prefix):
            cleaned = suffix
        else:
            return None

    if len(cleaned) != _EXPECTED_MAC_HEX_LENGTH or not all(
        c in "0123456789ABCDEF" for c in cleaned
    ):
        return None

    return ":".join(
        cleaned[i : i + 2] for i in range(0, _EXPECTED_MAC_HEX_LENGTH, 2)
    )


def load_font_choices() -> Tuple[List[str], Optional[str]]:
    try:
        fonts_path = _FONTS_DIR
        choices: List[str] = []
        if fonts_path.exists():
            entries = {
                entry.name
                for entry in fonts_path.iterdir()
                if (
                    entry.is_file()
                    and not entry.name.startswith(".")
                    and entry.suffix.lower() in FONT_FILE_EXTENSIONS
                )
            }
            choices = sorted(entries, key=str.lower)
        if not choices:
            choices = [DEFAULT_IMAGE_FONT]
        if DEFAULT_IMAGE_FONT not in choices:
            choices.insert(0, DEFAULT_IMAGE_FONT)
        return choices, None
    except OSError:
        logger.exception("Failed to read font directory %s", _FONTS_DIR)
        return [DEFAULT_IMAGE_FONT], "We couldn't load the font options. Please refresh the page."
