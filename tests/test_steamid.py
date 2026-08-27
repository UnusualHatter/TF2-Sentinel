import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from lib.steamid import account_id, to_steam3, to_steam64, steam2_to_64, steam3_to_64

class TestSteamID(unittest.TestCase):
    def test_account_id(self):
        self.assertEqual(account_id("76561197970748425"), 10482697)
        self.assertEqual(account_id(76561197970748425), 10482697)
        
    def test_to_steam3(self):
        self.assertEqual(to_steam3(76561197970748425), "[U:1:10482697]")
        self.assertEqual(to_steam3("76561197970748425"), "[U:1:10482697]")
        
    def test_to_steam64(self):
        self.assertEqual(to_steam64("76561197970748425"), 76561197970748425)
        self.assertEqual(to_steam64(" STEAM_0:1:5241348 "), 76561197970748425)
        self.assertEqual(to_steam64("[U:1:10482697]"), 76561197970748425)
        
    def test_malformed_steamid(self):
        self.assertIsNone(to_steam64("STEAM_0:3:5241348")) # invalid Y
        self.assertIsNone(to_steam64("[U:2:10482697]"))
        self.assertIsNone(to_steam64("76561197960265727")) # Below base
        self.assertIsNone(to_steam64("not an id"))

if __name__ == "__main__":
    unittest.main()
