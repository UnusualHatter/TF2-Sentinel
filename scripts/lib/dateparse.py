"""Best-effort parsing of the date formats SourceBans skins print.

Every install picks its own PHP date() format for the "Invoked on"
column, so this tries a list of known formats rather than one "correct"
pattern. Add a format here if a new source's dates come back empty.

Timestamps that carry a UTC offset are converted to UTC. Timestamps
without one are assumed to already be UTC: the pages don't state a
server timezone anywhere, so there is nothing better to assume, and
assuming the *scraping* machine's local timezone instead would make the
output depend on who ran the sync. These are a recency signal, not a
forensic record.
"""

from __future__ import annotations

import datetime as _dt

_FORMATS = [
    "%B %d, %Y, %I:%M %p",   # August 19, 2026, 10:27 pm
    "%Y-%m-%d %H:%M:%S",     # 2026-08-19 00:18:36
    "%b-%d-%Y %H:%M:%S",     # Aug-19-2026 20:41:24
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y - %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%d",
]

_PLACEHOLDERS = {"not applicable", "never", "n/a"}


def _to_utc_string(parsed: _dt.datetime) -> str:
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_to_iso(text: str | None) -> str | None:
    """Parse a free-form date string to `YYYY-MM-DDTHH:MM:SSZ`, or None."""
    if not text:
        return None
    text = text.strip()
    if not text or text.lower() in _PLACEHOLDERS:
        return None

    # Already ISO 8601 (the "modern" skin gives us this directly, with an
    # offset; some others print a naive "YYYY-MM-DD HH:MM:SS" that lands
    # here too).
    try:
        return _to_utc_string(_dt.datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        pass

    for fmt in _FORMATS:
        try:
            parsed = _dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
        return _to_utc_string(parsed)

    return None
