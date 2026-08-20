"""Cases the reason classifier is expected to get right.

Run with: python -m unittest discover -s tests

The strings here are real ban reasons taken from the imported sources
(trimmed, and with SteamIDs shortened), because the interesting cases are
the ones actual admins write, not the ones that are easy to invent.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.classify import classify_reason  # noqa: E402


class TestObviousCheating(unittest.TestCase):
    def test_plain_cheat_terms(self):
        for reason in [
            "Aimbot",
            "Aimbot/Wallhack",
            "aimbot, double tapping",
            "Auto-Ban: Cheating/Multi-Hack (Lmaobox)",
            "[StAC] Banned for cheating. Demo file: auto-20260819-2116-pl_odyssey.dem",
            "SMAC 0.8.8.0: Aimbot Detected",
            "Uso de cheat",
            "Trapaça",
        ]:
            with self.subTest(reason=reason):
                self.assertEqual(classify_reason(reason), "cheater")


class TestNotACheatingDetermination(unittest.TestCase):
    """Reasons that mention cheating but do not accuse *this* account."""

    def test_association_is_not_cheating(self):
        for reason in [
            "Associação com cheater, jogando casual em party com cheater",
            "Associação com cheaters. CHEATER [L1.49]",
            "Member of a hacker group",
        ]:
            with self.subTest(reason=reason):
                self.assertEqual(classify_reason(reason), "server_ban")

    def test_alt_of_a_banned_account_is_not_cheating(self):
        for reason in [
            "Alt de cheater, main: STEAM_0:0:4385",
            "Conta alternativa de cheater já banido",
            "[SourceSleuth] Duplicate account",
        ]:
            with self.subTest(reason=reason):
                self.assertEqual(classify_reason(reason), "server_ban")

    def test_compromised_account_is_the_victim(self):
        # The player was hacked, not hacking.
        for reason in [
            "Canceled donation on trade hold. Seems like he was hacked",
            "Account hacked, owner recovered it",
        ]:
            with self.subTest(reason=reason):
                self.assertEqual(classify_reason(reason), "server_ban")

    def test_conduct_bans_carry_no_cheat_weight(self):
        for reason in [
            "Inappropriate Language",
            "troll",
            "' Toxicity '",
            "mic spam",
            "Abuso de Exploit",
            "Scammer. Alt of OG",
            "!calladmin abuse",
        ]:
            with self.subTest(reason=reason):
                self.assertEqual(classify_reason(reason), "server_ban")


class TestBotHosting(unittest.TestCase):
    def test_bot_hosting_is_its_own_category(self):
        for reason in ["Bot Hoster", "Owner of bot hosting groups"]:
            with self.subTest(reason=reason):
                self.assertEqual(classify_reason(reason), "bot")

    def test_cheating_wins_over_bot_hosting(self):
        # Using cheats is the stronger, more specific claim about the account.
        self.assertEqual(classify_reason("Uso de cheat, hoster de bot"), "cheater")


class TestFallback(unittest.TestCase):
    def test_unrecognised_text_is_conservative(self):
        for reason in ["", "0", "-", "/noreason", "1 de abril"]:
            with self.subTest(reason=reason):
                self.assertEqual(classify_reason(reason), "server_ban")


if __name__ == "__main__":
    unittest.main()
