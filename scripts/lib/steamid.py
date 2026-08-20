"""Conversions between the SteamID formats sources use and SteamID64.

TF2 Sentinel keys every account by SteamID64 (see ``accounts.steamid64`` in
``db/init/001_schema.sql``). Upstream sources hand back a mix of formats,
so every importer normalizes through this module rather than rolling its
own math.
"""

from __future__ import annotations

import re

# SteamID64 of the lowest valid individual account (steam3 [U:1:0]).
# Not a typo, just Valve's ID space starting a long way from zero.
_BASE = 76561197960265728

_STEAM2_RE = re.compile(r"^STEAM_([0-5]):([01]):(\d+)$", re.IGNORECASE)
_STEAM3_RE = re.compile(r"^\[U:1:(\d+)\]$")


def steam2_to_64(value: str) -> int | None:
    """Convert ``STEAM_X:Y:Z`` to a SteamID64. Returns None if malformed."""
    m = _STEAM2_RE.match(value.strip())
    if not m:
        return None
    y, z = int(m.group(2)), int(m.group(3))
    return _BASE + z * 2 + y


def steam3_to_64(value: str) -> int | None:
    """Convert ``[U:1:N]`` to a SteamID64. Returns None if malformed."""
    m = _STEAM3_RE.match(value.strip())
    if not m:
        return None
    return _BASE + int(m.group(1))


def to_steam64(value: str) -> int | None:
    """Best-effort conversion of any of steam2 / steam3 / bare SteamID64."""
    value = value.strip()
    if value.isdigit():
        n = int(value)
        return n if _BASE <= n <= _BASE + 4294967295 else None
    if value.upper().startswith("STEAM_"):
        return steam2_to_64(value)
    if value.startswith("[U:1:"):
        return steam3_to_64(value)
    return None


def to_steam3(steamid64: int) -> str:
    """Render a SteamID64 as steam3 ``[U:1:N]`` for display/exports."""
    return f"[U:1:{steamid64 - _BASE}]"


def account_id(steamid64: int) -> int:
    """The account_id component the schema's CHECK constraint expects."""
    return steamid64 - _BASE
