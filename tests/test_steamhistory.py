"""Tests for the SteamHistory SourceBans importer."""

from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import fetch_steamhistory_bans as importer  # noqa: E402

KEY = "b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0b0"
ID_A = "76561198353460771"
ID_B = "76561198968423102"


def ban(steamid=ID_A, server="BlackWonder", reason="[Anti-Cheat] Aimbot Detected",
        state="Permanent", banned=1552662317, unbanned=0, name="player"):
    return {
        "SteamID": steamid, "Name": name, "CurrentState": state,
        "BanReason": reason, "UnbanReason": None,
        "BanTimestamp": banned, "UnbanTimestamp": unbanned, "Server": server,
    }


class FakeResponse:
    def __init__(self, payload):
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    def __init__(self, script):
        self.script = list(script)
        self.urls = []

    def open(self, request, timeout=None):
        self.urls.append(request.full_url)
        outcome = self.script.pop(0) if self.script else {"response": []}
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


def make_fetcher(script, attempts=importer.DEFAULT_ATTEMPTS):
    slept = []
    return importer.Fetcher(KEY, timeout=1.0, attempts=attempts, delay=0.0,
                            opener=FakeOpener(script), sleep=slept.append), slept


def http_error(code):
    return urllib.error.HTTPError("https://steamhistory.test/", code, "err", {}, BytesIO(b""))


class BatchingTests(unittest.TestCase):
    def test_batches_respect_the_documented_maximum(self):
        chunks = list(importer.batched([str(n) for n in range(250)], importer.MAX_BATCH))
        self.assertEqual([len(c) for c in chunks], [100, 100, 50])

    def test_duplicate_and_malformed_ids_are_dropped(self, ):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "accounts.json"
            path.write_text(json.dumps([
                {"steamid64": ID_A}, {"steamid64": ID_A}, {"steamid64": "nonsense"},
                {"steamid64": "8656119835346077"}, {"steamid64": None}, {"steamid64": ID_B},
                "not a row",
            ]))
            self.assertEqual(importer.load_account_ids(path), [ID_A, ID_B])


class ErrorHandlingTests(unittest.TestCase):
    def test_an_error_body_on_a_200_is_a_rejection_not_a_success(self):
        # The API answers HTTP 200 for a bad key, so the body is what matters.
        fetcher, _ = make_fetcher([{"error": "Invalid Key"}])
        with self.assertRaises(importer.SteamHistoryRejected):
            fetcher.batch([ID_A])
        self.assertEqual(fetcher.requests, 1, "a rejection must not be retried")

    def test_a_missing_key_is_a_rejection(self):
        fetcher, _ = make_fetcher([{"error": "No Key Parameter Provided"}])
        with self.assertRaises(importer.SteamHistoryRejected):
            fetcher.batch([ID_A])

    def test_the_key_is_sent_but_never_reported(self):
        fetcher, _ = make_fetcher([{"error": KEY + " is invalid"}])
        with self.assertRaises(importer.SteamHistoryRejected) as caught:
            fetcher.batch([ID_A])
        self.assertIn(KEY, fetcher.opener.urls[0])
        self.assertNotIn(KEY, str(caught.exception))

    def test_a_transient_failure_is_retried(self):
        fetcher, slept = make_fetcher([http_error(502), {"response": [ban()]}])
        self.assertEqual(len(fetcher.batch([ID_A])), 1)
        self.assertEqual(fetcher.requests, 2)
        self.assertEqual(len(slept), 1)

    def test_backoff_grows_and_then_gives_up(self):
        fetcher, slept = make_fetcher([http_error(500)] * 4)
        with self.assertRaises(importer.SteamHistoryUnavailable):
            fetcher.batch([ID_A])
        self.assertEqual(fetcher.requests, 4)
        self.assertLess(slept[0], slept[1])
        self.assertLess(slept[1], slept[2])

    def test_a_timeout_is_retried_then_reported(self):
        fetcher, _ = make_fetcher([TimeoutError("timed out")] * 4)
        with self.assertRaises(importer.SteamHistoryUnavailable) as caught:
            fetcher.batch([ID_A])
        self.assertIn("TimeoutError", str(caught.exception))

    def test_html_instead_of_json_is_a_failure_not_a_crash(self):
        fetcher, _ = make_fetcher([b"<html>cloudflare</html>"] * 4)
        with self.assertRaises(importer.SteamHistoryUnavailable):
            fetcher.batch([ID_A])

    def test_an_empty_response_is_not_an_error(self):
        fetcher, _ = make_fetcher([{"response": []}])
        self.assertEqual(fetcher.batch([ID_A]), [])
        fetcher, _ = make_fetcher([{}])
        self.assertEqual(fetcher.batch([ID_A]), [])

    def test_the_shouldkey_response_shape_is_understood(self):
        fetcher, _ = make_fetcher([{"response": {ID_A: [ban()], ID_B: [ban(steamid=ID_B)]}}])
        self.assertEqual(len(fetcher.batch([ID_A, ID_B])), 2)


class NormalizeTests(unittest.TestCase):
    def test_a_record_keeps_the_community_that_issued_the_ban(self):
        record = importer.normalize_record(ban(), {ID_A})
        self.assertEqual(record["server"], "BlackWonder")
        self.assertEqual(record["via"], "steamhistory")
        self.assertEqual(record["steamid64"], ID_A)

    def test_the_reason_goes_through_the_pipeline_classifier(self):
        self.assertEqual(importer.normalize_record(ban(reason="Aimbot"), {ID_A})["flag"], "cheater")
        self.assertEqual(
            importer.normalize_record(ban(reason="Associação com cheater"), {ID_A})["flag"],
            "server_ban")
        self.assertEqual(importer.normalize_record(ban(reason=None), {ID_A})["flag"], "server_ban")

    def test_only_permanent_and_temporary_bans_count_as_active(self):
        for state, active in [("Permanent", True), ("Temp-Ban", True),
                              ("Expired", False), ("Unbanned", False)]:
            self.assertEqual(importer.normalize_record(ban(state=state), {ID_A})["active"], active)

    def test_null_text_fields_become_empty_strings(self):
        record = importer.normalize_record(ban(name=None, reason=None), {ID_A})
        self.assertEqual(record["name"], "")
        self.assertEqual(record["reason"], "")
        self.assertEqual(record["unban_reason"], "")

    def test_unusable_timestamps_become_zero(self):
        for value in (None, "yesterday", -5, 0, True, 99999999999):
            record = importer.normalize_record(ban(banned=value), {ID_A})
            self.assertEqual(record["banned_at"], 0, f"for {value!r}")

    def test_records_for_unusable_or_unrequested_accounts_are_dropped(self):
        self.assertIsNone(importer.normalize_record(ban(steamid="12345"), {ID_A}))
        self.assertIsNone(importer.normalize_record(ban(steamid=ID_B), {ID_A}))
        self.assertIsNone(importer.normalize_record(ban(server=""), {ID_A}))
        self.assertIsNone(importer.normalize_record(ban(server=None), {ID_A}))
        self.assertIsNone(importer.normalize_record("not a record", {ID_A}))


class CollectTests(unittest.TestCase):
    def test_identical_records_are_only_kept_once(self):
        fetcher, _ = make_fetcher([{"response": [ban(), ban(), ban(server="Skial")]}])
        records, failed, queried = importer.collect([ID_A], fetcher, 100, 1, log=lambda *a: None)
        self.assertEqual(len(records), 2)
        self.assertEqual((failed, queried), (0, 1))

    def test_a_failed_batch_does_not_lose_the_others(self):
        fetcher, _ = make_fetcher([
            {"response": [ban()]},
            http_error(500), http_error(500), http_error(500), http_error(500),
        ])
        records, failed, queried = importer.collect([ID_A, ID_B], fetcher, 1, 1,
                                                    log=lambda *a: None)
        self.assertEqual(len(records), 1)
        self.assertEqual(failed, 1)
        self.assertEqual(queried, 1, "only the batch that answered counts as queried")

    def test_a_rejection_stops_the_whole_run(self):
        fetcher, _ = make_fetcher([{"error": "Invalid Key"}, {"error": "Invalid Key"}])
        with self.assertRaises(importer.SteamHistoryRejected):
            importer.collect([ID_A, ID_B], fetcher, 1, 1, log=lambda *a: None)

    def test_output_does_not_depend_on_which_batch_finishes_first(self):
        script = [{"response": [ban(steamid=ID_A)]}, {"response": [ban(steamid=ID_B)]}]
        one, _ = make_fetcher(list(script))
        four, _ = make_fetcher(list(script))
        a, _, _ = importer.collect([ID_A, ID_B], one, 1, 1, log=lambda *a: None)
        b, _, _ = importer.collect([ID_A, ID_B], four, 1, 4, log=lambda *a: None)
        self.assertEqual(a, b)


class MatcherTests(unittest.TestCase):
    CATALOG = [
        {"slug": "blackwonder-sourcebans", "name": "BlackWonder", "short_name": "BlackWonder"},
        {"slug": "panda-sourcebans", "name": "Panda Community", "short_name": "Panda"},
        {"slug": "discff-community-bans", "name": "DISC-FF", "short_name": "DISC-FF"},
        {"slug": "ugc-direct-cheating-bans", "name": "UGC", "short_name": "UGC"},
        {"slug": "ugc-mirror-bans", "name": "UGC mirror", "short_name": "UGC"},
    ]

    def setUp(self):
        self.match = importer.source_matcher(self.CATALOG)

    def test_a_community_already_imported_is_recognised(self):
        for server, slug in [("BlackWonder", "blackwonder-sourcebans"),
                             ("Panda-Community", "panda-sourcebans"),
                             ("DISC-FF", "discff-community-bans")]:
            slugs, confidence = self.match(server)
            self.assertIn(slug, slugs, server)
            self.assertIn(confidence, ("exact", "prefix"))

    def test_an_ambiguous_name_reports_every_candidate(self):
        slugs, confidence = self.match("UGC-Gaming")
        self.assertEqual(confidence, "prefix")
        self.assertEqual(sorted(slugs), ["ugc-direct-cheating-bans", "ugc-mirror-bans"])

    def test_an_unknown_community_matches_nothing(self):
        self.assertEqual(self.match("Sappho.io"), ([], "none"))
        self.assertEqual(self.match(""), ([], "none"))

    def test_the_summary_separates_new_communities_from_mirrors(self):
        # Deduplication is collect()'s job; the summary counts what it is given.
        records = [
            importer.normalize_record(ban(server="BlackWonder", banned=1), {ID_A}),
            importer.normalize_record(ban(server="BlackWonder", banned=2, steamid=ID_B), {ID_B}),
            importer.normalize_record(ban(server="Sappho.io", reason="hacking"), {ID_A}),
        ]
        rows = importer.summarize_servers(records, self.match)
        by_server = {row["server"]: row for row in rows}
        self.assertEqual(by_server["BlackWonder"]["records"], 2)
        self.assertEqual(by_server["BlackWonder"]["accounts"], 2)
        self.assertEqual(by_server["BlackWonder"]["registered_sources"],
                         ["blackwonder-sourcebans"])
        self.assertEqual(by_server["Sappho.io"]["registered_sources"], [],
                         "an unimported community is new evidence, not a mirror")
        self.assertEqual(by_server["Sappho.io"]["cheating_reasons"], 1)


if __name__ == "__main__":
    unittest.main()
