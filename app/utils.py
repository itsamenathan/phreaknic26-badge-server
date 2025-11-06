from __future__ import annotations

import re
from typing import Optional, Union

_MAC_CLEAN_RE = re.compile(r"[^0-9A-Fa-f]")


def _bytes_to_hex(mac_bytes: bytes) -> str:
    return mac_bytes.hex().upper()


def normalise_mac_address(value: Union[str, bytes, bytearray, int]) -> Optional[str]:
    """
    Return MAC address in AA:BB:CC:DD:EE:FF format or None if invalid.

    Accepted inputs:
      * Strings in any common separator style (AA:BB:..., AA-BB-..., AABBCC..., etc.)
      * Six-byte `bytes` / `bytearray` objects
      * Integers in the range [0, 0xFFFFFFFFFFFF]
    """
    if value is None:
        return None

    if isinstance(value, (bytes, bytearray)):
        if len(value) != 6:
            # Allow leading-zero-padded 8-byte values (drop the upper bytes if zero)
            if len(value) > 6 and all(b == 0 for b in value[:-6]):
                value = value[-6:]
            else:
                return None
        cleaned = _bytes_to_hex(value)
    elif isinstance(value, int):
        if value < 0 or value > 0xFFFFFFFFFFFF:
            return None
        cleaned = f"{value:012X}"
    else:
        text = str(value).strip()
        if not text:
                return None
        cleaned = _MAC_CLEAN_RE.sub("", text).upper()

    if len(cleaned) > 12:
        prefix = cleaned[: len(cleaned) - 12]
        suffix = cleaned[-12:]
        if not prefix or all(ch == "0" for ch in prefix):
            cleaned = suffix
        else:
            return None

    if len(cleaned) != 12 or not all(c in "0123456789ABCDEF" for c in cleaned):
        return None

    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))
