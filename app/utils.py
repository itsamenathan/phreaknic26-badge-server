from __future__ import annotations

import re
from typing import Optional, Union

_MAC_CLEAN_RE = re.compile(r"[^0-9A-Fa-f]")
_EXPECTED_MAC_BYTES = 8
_EXPECTED_MAC_HEX_LENGTH = _EXPECTED_MAC_BYTES * 2
_MAX_MAC_INT = (1 << (_EXPECTED_MAC_BYTES * 8)) - 1


def _bytes_to_hex(mac_bytes: bytes) -> str:
    return mac_bytes.hex().upper()


def normalise_mac_address(value: Union[str, bytes, bytearray, int]) -> Optional[str]:
    """
    Return MAC address in AA:BB:CC:DD:EE:FF:GG:HH format or None if invalid.

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
