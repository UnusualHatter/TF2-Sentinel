"""Turn a free-text ban/list reason into a Sentinel confidence flag.

Mirrors the import policy from SOURCES.md: records are kept in full for
provenance, but only reasons that are an explicit cheating determination
carry confidence weight. Association, alt-account, exploit-abuse and
conduct bans are recorded as `server_ban` and contribute nothing.

Reasons are free text written by many different server admins in at
least English and Portuguese, so this is a keyword classifier rather
than anything smarter and unusual phrasing will slip through. Unmatched
text falls back to `server_ban` (provenance only, zero weight), which is
the safe side to be wrong on.

EXCLUDE is checked before CHEAT because reasons like "Associação com
cheater" (association with a cheater) contain a cheat keyword but are
not a cheating determination for the banned account itself.

See tests/test_classify.py for the cases this is expected to get right,
including the ones it is deliberately conservative about.
"""

from __future__ import annotations

import re

# Checked first. Any match => 'server_ban' (provenance only, zero weight),
# regardless of whether a cheat keyword also appears in the same reason.
_EXCLUDE_PATTERNS = [
    r"associa\w*",                 # association / associação
    r"\balt\b|alt\s*account|conta\s*alternativa",
    r"duplicate\s*account|duplicidade|\[sourcesleuth\]",
    r"ban\s*evasion|evas[aã]o",
    r"exploit",
    r"calladmin|call\s*admin",
    r"vote\s*(ban|kick)\s*abuse|abuso de vote|mass\s*vote",
    r"advertis|propaganda",
    r"\bspam\b|micspam",
    r"rac[ei]s|slur|swastika|nazi",
    r"harass|ass[eé]dio",
    r"toxic|toxicidade",
    r"transphob|homophob",
    r"inappropriate|inadequad",
    r"begging|mendig",
    r"griefing|team\s*kill|teamkill",
    r"disrespect|desrespeito",
    r"scammer|scam\b",             # trading dispute, not an anti-cheat verdict
    # Belonging to a cheating group, or having been the victim of a
    # compromised account, is not a cheating determination for this account.
    r"hacker\s*group",
    r"(was|got|been)\s+hacked|account\s+hacked|conta\s+hackeada",
]

# Checked second. Any match => 'cheater'.
_CHEAT_PATTERNS = [
    r"cheat",
    r"hack",                       # hack, hacking, hacker, wallhack, ...
    r"aim\s*-?\s*bot",
    r"wall\s*-?\s*hack",
    r"\besp\b",
    r"silent\s*aim",
    r"spin\s*-?\s*bot",
    r"trigger\s*-?\s*bot",
    r"multi\s*-?\s*hack",
    r"lmaobox",
    r"legit\s*-?\s*bot",
    r"rage\s*-?\s*bot",
    r"no\s*-?\s*recoil",
    r"speed\s*-?\s*hack",
    r"fly\s*-?\s*hack",
    r"god\s*-?\s*mode",
    r"anti-?aim",
    r"\bstac\b|\bsmac\b|\[ac\]|little anti[\s-]cheat|anti-?cheat\s*(detect|detec)",
    r"trapa[cç]",                  # trapaça / trapacear / trapaceiro
]

# Checked last, and narrower than CHEAT: accounts that host or run cheat
# bots rather than accounts that use an aimbot themselves. Rare in
# SourceBans data; most 'bot' classification comes from tf2bd-style lists,
# which are imported by a different path.
_BOT_PATTERNS = [
    r"bot\s*host|host(ing)?\s*.{0,15}\bbot",
    r"member of a bot",
    r"owner of.{0,10}\bbot",
]

_exclude_re = re.compile("|".join(_EXCLUDE_PATTERNS), re.IGNORECASE)
_cheat_re = re.compile("|".join(_CHEAT_PATTERNS), re.IGNORECASE)
_bot_re = re.compile("|".join(_BOT_PATTERNS), re.IGNORECASE)


def classify_reason(reason: str) -> str:
    """Classify a ban/list reason as 'cheater', 'bot', or 'server_ban'."""
    if not reason:
        return "server_ban"
    if _exclude_re.search(reason):
        return "server_ban"
    if _cheat_re.search(reason):
        return "cheater"
    if _bot_re.search(reason):
        return "bot"
    return "server_ban"
