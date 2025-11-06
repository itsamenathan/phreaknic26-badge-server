from __future__ import annotations

import re
from typing import Optional

_MAC_CLEAN_RE = re.compile(r"[^0-9A-Fa-f]")


def normalise_mac_address(value: str) -> Optional[str]:
    """Return MAC address in AA:BB:CC:DD:EE:FF format or None if invalid."""
    if not value:
        return None

    cleaned = _MAC_CLEAN_RE.sub("", value).upper()
    if len(cleaned) != 12 or not all(c in "0123456789ABCDEF" for c in cleaned):
        return None

    return ":".join(cleaned[i : i + 2] for i in range(0, 12, 2))
