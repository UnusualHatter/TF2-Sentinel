"""Parser for SourceBans ban-list pages.

SourceBans is the ban-management plugin most public TF2 community
servers run, but its front end has shipped in at least three different
skins over the years and communities customize them further. Rather
than one parser per site, this recognizes the handful of HTML shapes
that keep showing up and picks whichever one matches:

  * ``modern``  - a data table with ``data-testid="ban-row"`` rows and
    the reason in a ``title`` attribute (newer SourceBans::Web builds).
  * ``classic`` - the original skin: "Ban Details" panels containing
    ``listtable_1`` label/value cell pairs, including a direct
    SteamCommunity profile link.
  * ``card``    - a card-based skin: ``ban_list_detal`` blocks with
    ``<li><span>label</span><span>value</span></li>`` rows.

Each returns the same shape: a list of dicts with whatever of
``name`` / ``steam2`` / ``steamid64`` / ``reason`` / ``date_iso`` /
``admin`` / ``active`` the page exposed. Fields the page didn't have
are simply absent — callers merging into ``source_records`` decide
what's required.

The parsing is regex-based rather than a real HTML parser to keep the
project dependency-free (see scripts/README.md). That is a reasonable
trade for a handful of known, cooperative pages; it would not be for
untrusted input.
"""

from __future__ import annotations

import html as html_lib
import re
from typing import Any

from .steamid import steam2_to_64

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    text = _TAG_RE.sub(" ", text)
    text = html_lib.unescape(text)
    return _WS_RE.sub(" ", text).strip()


# ---------------------------------------------------------------- modern --

_MODERN_ROW_RE = re.compile(
    r'<tr[^>]*data-testid="ban-row"[^>]*>(?P<body>.*?)</tr>', re.DOTALL
)
_MODERN_NAME_RE = re.compile(
    r'data-testid="drawer-trigger"[^>]*>(?P<name>.*?)</a>', re.DOTALL
)
_MODERN_STEAM2_RE = re.compile(r"(STEAM_[0-5]:[01]:\d+)")
_MODERN_REASON_RE = re.compile(
    r'class="[^"]*text-muted truncate[^"]*"[^>]*?title="(?P<reason>[^"]*)"', re.DOTALL
)
_MODERN_ADMIN_RE = re.compile(
    r'class="col-admin[^"]*"[^>]*>(?P<admin>.*?)</td>', re.DOTALL
)
_MODERN_DATE_RE = re.compile(r'<time datetime="(?P<iso>[^"]+)"')
_MODERN_STATUS_RE = re.compile(r'data-state="(?P<status>[a-z]+)"')


def _parse_modern(html: str) -> list[dict[str, Any]]:
    rows = []
    for m in _MODERN_ROW_RE.finditer(html):
        body = m.group("body")
        steam_m = _MODERN_STEAM2_RE.search(body)
        if not steam_m:
            continue
        name_m = _MODERN_NAME_RE.search(body)
        reason_m = _MODERN_REASON_RE.search(body)
        admin_m = _MODERN_ADMIN_RE.search(body)
        date_m = _MODERN_DATE_RE.search(body)
        status_m = _MODERN_STATUS_RE.search(m.group(0))
        rows.append(
            {
                "steam2": steam_m.group(1),
                "name": _clean(name_m.group("name")) if name_m else "",
                "reason": _clean(reason_m.group("reason")) if reason_m else "",
                "admin": _clean(admin_m.group("admin")) if admin_m else "",
                "date_iso": date_m.group("iso") if date_m else "",
                "active": (status_m.group("status") not in ("expired", "unbanned"))
                if status_m
                else None,
            }
        )
    return rows


# ------------------------------------------------- classic and card skins --

# Both of these render one labelled block per ban, differing only in how the
# block is delimited and how a label/value pair is marked up, so they share
# the extraction loop below.

_PROFILE_RE = re.compile(r"steamcommunity\.com/profiles/(\d{17})")

# Label text (lowercased) -> the field name we store it under. Both skins draw
# from this one table; a label only one of them uses is harmless to the other.
_LABELS = {
    "player": "name",
    "name": "name",
    "steam id": "steam2",
    "steamid": "steam2",
    "steam community": "steamid64_text",
    "invoked on": "date_text",
    "date": "date_text",
    "reason": "reason",
    "banlength": "ban_length",
    "ban length": "ban_length",
    "banned by": "admin",
    "admin": "admin",
}

# "listtable_1", "listtable_11", ...: at least one install renumbers the class
# per row. The value cell shares the label cell's class, while the neighbouring
# admin-controls cell ends in a different digit ("listtable_2", "listtable_22"),
# so requiring a trailing 1 keeps the pairs and drops the controls.
_LISTTABLE_LABEL_CLASS = r"listtable_\d*1"
_CLASSIC_PAIR_RE = re.compile(
    r'class="' + _LISTTABLE_LABEL_CLASS + r'"[^>]*>\s*(?P<label>[^<]*?)\s*</td>\s*'
    r'<td[^>]*class="' + _LISTTABLE_LABEL_CLASS + r'"[^>]*>(?P<value>.*?)</td>',
    re.DOTALL,
)
_CARD_PAIR_RE = re.compile(
    r"<li>\s*<span[^>]*>(?P<label>.*?)</span>\s*<span[^>]*>(?P<value>.*?)</span>\s*</li>",
    re.DOTALL,
)

_CARD_BLOCK_SPLIT_RE = re.compile(r'class="ban_list_detal[^"]*"')


def _parse_labelled_blocks(blocks: list[str], pair_re: re.Pattern) -> list[dict[str, Any]]:
    rows = []
    for block in blocks:
        fields: dict[str, str] = {}
        for pm in pair_re.finditer(block):
            key = _LABELS.get(_clean(pm.group("label")).lower())
            if not key:
                continue
            value_html = pm.group("value")
            if key == "steamid64_text":
                # This cell is a link to the profile; the id is in the href.
                profile = _PROFILE_RE.search(value_html)
                if profile:
                    fields["steamid64"] = profile.group(1)
                continue
            fields[key] = _clean(value_html)
        if "steam2" in fields or "steamid64" in fields:
            rows.append(fields)
    return rows


def parse(html: str) -> list[dict[str, Any]]:
    """Parse a SourceBans ban-list HTML page, auto-detecting the skin."""
    if 'data-testid="ban-row"' in html:
        return _parse_modern(html)
    if "Ban Details" in html:
        # Everything before the first heading is page chrome, not a ban.
        return _parse_labelled_blocks(html.split("Ban Details")[1:], _CLASSIC_PAIR_RE)
    if "ban_list_detal" in html:
        return _parse_labelled_blocks(_CARD_BLOCK_SPLIT_RE.split(html)[1:], _CARD_PAIR_RE)
    return []


def resolve_steamid64(row: dict[str, Any]) -> int | None:
    """Get a row's SteamID64, converting from steam2 if there's no direct one."""
    if row.get("steamid64"):
        try:
            return int(row["steamid64"])
        except ValueError:
            return None
    if row.get("steam2"):
        return steam2_to_64(row["steam2"])
    return None
