"""Tests for the SteamHistory merge, on a throwaway copy of the database."""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import merge_steamhistory as merge  # noqa: E402

ID_A = "76561198353460771"
ID_B = "76561198968423102"

SCHEMA = {
    "sources.csv": ["source_id", "slug", "name", "source_type", "upstream_repo", "update_url",
                    "authors", "scope_region", "description", "source_file"],
    "source_profiles.csv": ["source_id", "base_weight", "evidence_class", "independence_group",
                            "counts_toward_confidence", "is_mirror", "assessment_method",
                            "last_verified", "notes"],
    "accounts.csv": ["steamid64", "account_id", "steam3", "first_observed_at", "last_observed_at"],
    "source_records.csv": ["source_record_id", "source_id", "steamid64", "raw_steam_id",
                           "record_index", "normalization_note", "record_hash", "raw_record"],
    "flags.csv": ["flag_id", "steamid64", "source_id", "flag", "review_status", "active",
                  "observed_at"],
    "aliases.csv": ["alias_id", "steamid64", "source_id", "player_name", "observed_at"],
    "evidence.csv": ["evidence_id", "steamid64", "source_id", "evidence_type", "content",
                     "observed_at"],
}

SERVER_TABLE = [
    {"server": "BlackWonder", "decision": "map", "source_slug": "blackwonder-sourcebans",
     "name": "", "scope_region": "", "base_weight": "", "independence_group": "", "notes": ""},
    {"server": "dpg.tf", "decision": "register", "source_slug": "dpg-tf-sourcebans",
     "name": "dpg.tf — community bans", "scope_region": "global", "base_weight": "78",
     "independence_group": "dpg-tf", "notes": "new community"},
    {"server": "Rustopia", "decision": "skip", "source_slug": "", "name": "", "scope_region": "",
     "base_weight": "", "independence_group": "", "notes": "not TF2"},
]


def record(steamid=ID_A, server="BlackWonder", reason="Aimbot", banned=1552662317,
           active=True, name="player", state="Permanent"):
    return {"steamid64": steamid, "name": name, "server": server, "state": state,
            "active": active, "reason": reason, "unban_reason": "", "banned_at": banned,
            "unbanned_at": 0, "flag": "cheater", "via": "steamhistory"}


class MergeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "normalized"
        self.data.mkdir()
        self._real_dir = merge.DATA_DIR
        merge.DATA_DIR = self.data
        self.addCleanup(lambda: setattr(merge, "DATA_DIR", self._real_dir))

        for name, fields in SCHEMA.items():
            self.write(name, fields, [])
        self.write("sources.csv", SCHEMA["sources.csv"], [{
            "source_id": "1", "slug": "blackwonder-sourcebans", "name": "BlackWonder",
            "source_type": "sourcebans", "upstream_repo": "", "update_url": "", "authors": "",
            "scope_region": "global", "description": "", "source_file": "",
        }])
        self.write("source_profiles.csv", SCHEMA["source_profiles.csv"], [{
            "source_id": "1", "base_weight": "92", "evidence_class": "strong",
            "independence_group": "blackwonder", "counts_toward_confidence": "true",
            "is_mirror": "false", "assessment_method": "community-ban", "last_verified": "",
            "notes": "",
        }])
        self.write("accounts.csv", SCHEMA["accounts.csv"], [
            {"steamid64": ID_A, "account_id": "393195043", "steam3": "[U:1:393195043]",
             "first_observed_at": "", "last_observed_at": ""},
            {"steamid64": ID_B, "account_id": "1008157374", "steam3": "[U:1:1008157374]",
             "first_observed_at": "", "last_observed_at": ""},
        ])

        self.servers = self.root / "servers.csv"
        with self.servers.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(SERVER_TABLE[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(SERVER_TABLE)

    def write(self, name, fields, rows):
        with (self.data / name).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    def read(self, name):
        with (self.data / name).open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def run_merge(self, records, extra=()):
        path = self.root / "records.json"
        path.write_text(json.dumps({"records": records}), encoding="utf-8")
        return merge.main(["--records", str(path), "--servers", str(self.servers), *extra])

    def test_a_mapped_community_attaches_to_the_source_it_already_has(self):
        self.assertEqual(self.run_merge([record()]), 0)
        records = self.read("source_records.csv")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_id"], "1")
        self.assertEqual(records[0]["normalization_note"], "via steamhistory")
        self.assertEqual(len(self.read("sources.csv")), 1, "no new source for a known community")

    def test_a_new_community_gets_a_source_with_the_configured_weight(self):
        self.assertEqual(self.run_merge([record(server="dpg.tf")]), 0)
        sources = self.read("sources.csv")
        self.assertEqual(len(sources), 2)
        new = [s for s in sources if s["slug"] == "dpg-tf-sourcebans"][0]
        self.assertEqual(new["source_type"], "sourcebans")
        profile = [p for p in self.read("source_profiles.csv") if p["source_id"] == new["source_id"]][0]
        self.assertEqual(profile["base_weight"], "78")
        self.assertEqual(profile["independence_group"], "dpg-tf")
        self.assertEqual(profile["counts_toward_confidence"], "true")
        self.assertEqual(profile["is_mirror"], "false")

    def test_a_community_marked_skip_is_left_out(self):
        self.assertEqual(self.run_merge([record(server="Rustopia")]), 0)
        self.assertEqual(self.read("source_records.csv"), [])

    def test_a_community_missing_from_the_table_is_left_out(self):
        # Guessing at a community would put unrelated bans in a TF2 database.
        self.assertEqual(self.run_merge([record(server="Some New Server")]), 0)
        self.assertEqual(self.read("source_records.csv"), [])
        self.assertEqual(self.read("sources.csv")[0]["slug"], "blackwonder-sourcebans")

    def test_the_same_ban_twice_is_stored_once(self):
        self.run_merge([record(), record()])
        self.assertEqual(len(self.read("source_records.csv")), 1)
        self.run_merge([record()])
        self.assertEqual(len(self.read("source_records.csv")), 1, "re-running must be safe")

    def test_bans_differing_only_in_reason_or_date_are_both_kept(self):
        self.run_merge([record(), record(reason="Wallhack"), record(banned=1600000000)])
        self.assertEqual(len(self.read("source_records.csv")), 3)

    def test_one_flag_per_account_source_and_value(self):
        self.run_merge([record(), record(reason="Aimbot again")])
        flags = self.read("flags.csv")
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["flag"], "cheater")
        self.assertEqual(flags[0]["active"], "true")

    def test_an_expired_ban_is_recorded_as_inactive(self):
        self.run_merge([record(active=False, state="Expired")])
        self.assertEqual(self.read("flags.csv")[0]["active"], "false")

    def test_a_later_active_ban_reactivates_the_flag(self):
        self.run_merge([record(active=False, state="Expired")])
        self.assertEqual(self.read("flags.csv")[0]["active"], "false")
        self.run_merge([record(reason="Aimbot again", active=True)])
        self.assertEqual(self.read("flags.csv")[0]["active"], "true")

    def test_the_reason_decides_the_flag(self):
        self.run_merge([record(reason="Associação com cheater")])
        self.assertEqual(self.read("flags.csv")[0]["flag"], "server_ban")

    def test_the_ban_reason_is_kept_as_evidence_naming_the_community(self):
        self.run_merge([record()])
        evidence = self.read("evidence.csv")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["content"], "[BlackWonder ban] Aimbot")
        self.assertEqual(evidence[0]["evidence_type"], "source_note")

    def test_the_player_name_is_kept_as_an_alias(self):
        self.run_merge([record(name="someone")])
        aliases = self.read("aliases.csv")
        self.assertEqual([a["player_name"] for a in aliases], ["someone"])
        self.run_merge([record(reason="other", name="someone")])
        self.assertEqual(len(self.read("aliases.csv")), 1, "the same alias is not repeated")

    def test_an_account_not_in_the_database_is_skipped(self):
        self.assertEqual(self.run_merge([record(steamid="76561199999999999")]), 0)
        self.assertEqual(self.read("source_records.csv"), [])

    def test_the_ban_date_updates_when_the_account_was_first_seen(self):
        self.run_merge([record(banned=1552662317)])
        account = [a for a in self.read("accounts.csv") if a["steamid64"] == ID_A][0]
        self.assertEqual(account["first_observed_at"], "2019-03-15T15:05:17Z")

    def test_an_unusable_timestamp_does_not_produce_a_date(self):
        self.run_merge([record(banned=0)])
        self.assertEqual(json.loads(self.read("source_records.csv")[0]["raw_record"])["date_iso"], "")

    def test_the_raw_record_keeps_the_community_and_the_route(self):
        self.run_merge([record()])
        raw = json.loads(self.read("source_records.csv")[0]["raw_record"])
        self.assertEqual(raw["server"], "BlackWonder")
        self.assertEqual(raw["via"], "steamhistory")
        self.assertEqual(raw["state"], "Permanent")

    def test_a_dry_run_changes_nothing(self):
        before = {name: (self.data / name).read_text() for name in SCHEMA}
        self.assertEqual(self.run_merge([record(), record(server="dpg.tf")], extra=("--dry-run",)), 0)
        for name, text in before.items():
            self.assertEqual((self.data / name).read_text(), text, name)


if __name__ == "__main__":
    unittest.main()
