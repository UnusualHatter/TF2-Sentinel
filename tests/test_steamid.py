"""SteamID conversions, checked against known-correct real IDs.

Run with: python -m unittest discover -s tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.steamid import account_id, steam2_to_64, steam3_to_64, to_steam3, to_steam64  # noqa: E402

# steam2, steam3, steamid64 for the same account. Taken from ban pages that
# happened to print all three, so the mapping is verified rather than assumed.
KNOWN = [
    ("STEAM_0:0:62210641", "[U:1:124421282]", 76561198084687010),
    ("STEAM_0:1:404196331", "[U:1:808392663]", 76561198768658391),
    ("STEAM_0:1:186057727", "[U:1:372115455]", 76561198332381183),
]


class TestConversions(unittest.TestCase):
    def test_steam2_to_64(self):
        for steam2, _, expected in KNOWN:
            with self.subTest(steam2=steam2):
                self.assertEqual(steam2_to_64(steam2), expected)

    def test_steam3_to_64(self):
        for _, steam3, expected in KNOWN:
            with self.subTest(steam3=steam3):
                self.assertEqual(steam3_to_64(steam3), expected)

    def test_to_steam3_round_trip(self):
        for _, steam3, steamid64 in KNOWN:
            with self.subTest(steamid64=steamid64):
                self.assertEqual(to_steam3(steamid64), steam3)

    def test_account_id_matches_schema_constraint(self):
        # db/init/001_schema.sql: steamid64 = 76561197960265728 + account_id
        for _, _, steamid64 in KNOWN:
            with self.subTest(steamid64=steamid64):
                self.assertEqual(76561197960265728 + account_id(steamid64), steamid64)

    def test_to_steam64_accepts_every_format(self):
        for steam2, steam3, expected in KNOWN:
            for value in (steam2, steam3, str(expected)):
                with self.subTest(value=value):
                    self.assertEqual(to_steam64(value), expected)


class TestRejectsJunk(unittest.TestCase):
    def test_malformed_input_returns_none(self):
        # "BOT" is what SourceBans prints for a server bot with no real ID;
        # it must not silently become a valid account.
        for value in ["", "BOT", "no nickname present", "STEAM_0:2:1", "[U:2:5]", "76561197960265727"]:
            with self.subTest(value=value):
                self.assertIsNone(to_steam64(value))

    def test_out_of_range_steamid64_rejected(self):
        self.assertIsNone(to_steam64("1"))
        self.assertIsNone(to_steam64("99999999999999999"))


if __name__ == "__main__":
    unittest.main()
