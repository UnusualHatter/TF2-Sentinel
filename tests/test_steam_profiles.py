"""Tests for the Steam profile cache and the workflow that refreshes it."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import refresh_steam_profiles as refresher  # noqa: E402
from lib import profiles  # noqa: E402

KEY = "0123456789ABCDEF0123456789ABCDEF"
AVATAR_A = "a" * 40
AVATAR_B = "b" * 40


def steamid(n: int) -> str:
    return profiles.steamid64_of(7960265728 + n)


def player(n: int, avatar: str = AVATAR_A, name: str = "player", visibility: int = 3) -> dict:
    return {
        "steamid": steamid(n),
        "personaname": name,
        "communityvisibilitystate": visibility,
        "avatarmedium": f"https://avatars.steamstatic.com/{avatar}_medium.jpg",
    }


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self.headers = {}
        self._body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeOpener:
    """Stands in for urllib's opener. `script` is one entry per call."""

    def __init__(self, script):
        self.script = list(script)
        self.urls = []

    def open(self, request, timeout=None):
        self.urls.append(request.full_url)
        outcome = self.script.pop(0) if self.script else {"players": []}
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)


def make_fetcher(script, attempts=refresher.DEFAULT_ATTEMPTS):
    slept = []
    fetcher = refresher.Fetcher(KEY, timeout=1.0, attempts=attempts, delay=0.0,
                               opener=FakeOpener(script), sleep=slept.append)
    return fetcher, slept


def http_error(code, retry_after=None):
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
    return urllib.error.HTTPError("https://api.steampowered.test/", code, "err", headers, BytesIO(b""))


class BatchingTests(unittest.TestCase):
    def test_batches_never_exceed_the_api_maximum(self):
        chunks = list(refresher.batched(list(range(250)), refresher.MAX_BATCH))
        self.assertEqual([len(c) for c in chunks], [100, 100, 50])
        self.assertTrue(all(len(c) <= refresher.MAX_BATCH for c in chunks))

    def test_batch_size_is_capped_by_the_command_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            accounts = Path(tmp) / "accounts.json"
            accounts.write_text(json.dumps([{"steamid64": steamid(1)}]))
            code = refresher.main(["--accounts", str(accounts),
                                   "--profiles", str(Path(tmp) / "profiles.json"),
                                   "--batch-size", "5000", "--dry-run"])
        self.assertEqual(code, 0)

    def test_duplicate_and_malformed_ids_are_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            accounts = Path(tmp) / "accounts.json"
            accounts.write_text(json.dumps([
                {"steamid64": steamid(1)},
                {"steamid64": steamid(1)},
                {"steamid64": "not a steamid"},
                {"steamid64": "76561197960265901x"},
                {"steamid64": None},
                {"steamid64": steamid(2)},
                "a string instead of a row",
            ]))
            ids, _ = refresher.load_account_ids(accounts)
        self.assertEqual(ids, [7960265729, 7960265730])

    def test_legacy_avatar_urls_are_carried_over_as_a_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            accounts = Path(tmp) / "accounts.json"
            accounts.write_text(json.dumps([{
                "steamid64": steamid(1),
                "steam_persona_name": "old name",
                "avatar_url": f"https://avatars.fastly.steamstatic.com/{AVATAR_A}_medium.jpg",
            }]))
            _, legacy = refresher.load_account_ids(accounts)
        self.assertEqual(legacy[7960265729]["hash"], AVATAR_A)
        self.assertEqual(legacy[7960265729]["name"], "old name")
        self.assertEqual(legacy[7960265729]["fetched"], 0)


class FetcherTests(unittest.TestCase):
    def test_a_successful_call_returns_the_players(self):
        fetcher, _ = make_fetcher([{"response": {"players": [player(1)]}}])
        players = fetcher.batch([7960265729])
        self.assertEqual(len(players), 1)
        self.assertEqual(fetcher.requests, 1)

    def test_the_api_key_is_sent_but_never_reported(self):
        fetcher, _ = make_fetcher([http_error(500), http_error(500), http_error(500), http_error(500)])
        with self.assertRaises(refresher.SteamUnavailable) as caught:
            fetcher.batch([7960265729])
        self.assertIn(KEY, fetcher.opener.urls[0])
        self.assertNotIn(KEY, str(caught.exception))

    def test_a_transient_failure_is_retried(self):
        fetcher, slept = make_fetcher([http_error(500), {"response": {"players": [player(1)]}}])
        self.assertEqual(len(fetcher.batch([7960265729])), 1)
        self.assertEqual(fetcher.requests, 2)
        self.assertEqual(len(slept), 1)

    def test_backoff_grows_between_attempts(self):
        fetcher, slept = make_fetcher([http_error(503)] * 4)
        with self.assertRaises(refresher.SteamUnavailable):
            fetcher.batch([7960265729])
        self.assertEqual(fetcher.requests, 4)
        self.assertEqual(len(slept), 3)
        self.assertLess(slept[0], slept[1])
        self.assertLess(slept[1], slept[2])

    def test_retry_after_is_honoured(self):
        fetcher, slept = make_fetcher([http_error(429, retry_after=7),
                                       {"response": {"players": [player(1)]}}])
        fetcher.batch([7960265729])
        self.assertGreaterEqual(slept[0], 7)
        self.assertLess(slept[0], 8)

    def test_a_timeout_is_retried_then_reported(self):
        fetcher, _ = make_fetcher([TimeoutError("timed out")] * 4)
        with self.assertRaises(refresher.SteamUnavailable) as caught:
            fetcher.batch([7960265729])
        self.assertIn("TimeoutError", str(caught.exception))

    def test_a_rejected_key_is_not_retried(self):
        fetcher, _ = make_fetcher([http_error(403)] * 4)
        with self.assertRaises(refresher.SteamUnavailable):
            fetcher.batch([7960265729])
        self.assertEqual(fetcher.requests, 1)

    def test_malformed_json_is_treated_as_a_failure(self):
        fetcher, _ = make_fetcher([b"<html>maintenance</html>"] * 4)
        with self.assertRaises(refresher.SteamUnavailable):
            fetcher.batch([7960265729])

    def test_a_response_without_players_is_empty_not_an_error(self):
        fetcher, _ = make_fetcher([{"response": {}}])
        self.assertEqual(fetcher.batch([7960265729]), [])


class MergeTests(unittest.TestCase):
    def test_a_changed_avatar_replaces_the_old_one(self):
        store = {7960265729: profiles.new_entry(name="p", hash_value=AVATAR_A, fetched=10,
                                                state=profiles.STATE_PUBLIC)}
        fetcher, _ = make_fetcher([{"response": {"players": [player(1, avatar=AVATAR_B)]}}])
        updated, changed, failed = refresher.refresh(store, [7960265729], fetcher, 100, 1, 20,
                                                     log=lambda *a: None)
        self.assertEqual((updated, changed, failed), (1, 1, 0))
        self.assertEqual(store[7960265729]["hash"], AVATAR_B)
        self.assertEqual(store[7960265729]["fetched"], 20)

    def test_an_unchanged_avatar_is_not_counted_as_a_change(self):
        store = {7960265729: profiles.new_entry(name="player", hash_value=AVATAR_A, fetched=10,
                                                state=profiles.STATE_PUBLIC)}
        fetcher, _ = make_fetcher([{"response": {"players": [player(1)]}}])
        _, changed, _ = refresher.refresh(store, [7960265729], fetcher, 100, 1, 20,
                                          log=lambda *a: None)
        self.assertEqual(changed, 0)

    def test_a_failed_batch_leaves_its_accounts_untouched(self):
        store = {
            7960265729: profiles.new_entry(name="kept", hash_value=AVATAR_A, fetched=10,
                                           state=profiles.STATE_PUBLIC),
            7960265730: profiles.new_entry(name="kept too", hash_value=AVATAR_A, fetched=10,
                                           state=profiles.STATE_PUBLIC),
        }
        fetcher, _ = make_fetcher([
            {"response": {"players": [player(1, avatar=AVATAR_B, name="new")]}},
            http_error(500), http_error(500), http_error(500), http_error(500),
        ])
        _, _, failed = refresher.refresh(store, [7960265729, 7960265730], fetcher, 1, 1, 20,
                                         log=lambda *a: None)
        self.assertEqual(failed, 1)
        self.assertEqual(store[7960265729]["hash"], AVATAR_B)
        self.assertEqual(store[7960265730]["hash"], AVATAR_A)
        self.assertEqual(store[7960265730]["fetched"], 10)

    def test_an_account_steam_does_not_return_keeps_its_avatar_and_is_marked_missing(self):
        store = {7960265729: profiles.new_entry(name="gone", hash_value=AVATAR_A, fetched=10,
                                                state=profiles.STATE_PUBLIC)}
        fetcher, _ = make_fetcher([{"response": {"players": []}}])
        refresher.refresh(store, [7960265729], fetcher, 100, 1, 20, log=lambda *a: None)
        self.assertEqual(store[7960265729]["hash"], AVATAR_A)
        self.assertEqual(store[7960265729]["state"], profiles.STATE_MISSING)
        self.assertEqual(store[7960265729]["fetched"], 20)

    def test_a_private_profile_is_stored_as_limited(self):
        store = {}
        fetcher, _ = make_fetcher([{"response": {"players": [player(1, visibility=1)]}}])
        refresher.refresh(store, [7960265729], fetcher, 100, 1, 20, log=lambda *a: None)
        self.assertEqual(store[7960265729]["state"], profiles.STATE_LIMITED)
        self.assertEqual(store[7960265729]["hash"], AVATAR_A)

    def test_a_player_with_no_usable_avatar_keeps_the_previous_one(self):
        store = {7960265729: profiles.new_entry(name="p", hash_value=AVATAR_A, fetched=10,
                                                state=profiles.STATE_PUBLIC)}
        broken = {"steamid": steamid(1), "personaname": "p", "communityvisibilitystate": 3,
                  "avatarmedium": "https://example.invalid/whatever.png"}
        fetcher, _ = make_fetcher([{"response": {"players": [broken]}}])
        refresher.refresh(store, [7960265729], fetcher, 100, 1, 20, log=lambda *a: None)
        self.assertEqual(store[7960265729]["hash"], AVATAR_A)

    def test_a_player_for_an_unrequested_id_is_ignored(self):
        store = {}
        junk = dict(player(1), steamid="12345")
        fetcher, _ = make_fetcher([{"response": {"players": [junk]}}])
        refresher.refresh(store, [7960265729], fetcher, 100, 1, 20, log=lambda *a: None)
        self.assertNotIn(7960265729, {k: v for k, v in store.items()
                                      if v["state"] != profiles.STATE_MISSING})

    def test_results_are_merged_in_batch_order_whatever_order_they_arrive_in(self):
        script = [{"response": {"players": [player(n)]}} for n in range(1, 6)]
        store_a, store_b = {}, {}
        targets = [7960265728 + n for n in range(1, 6)]
        fetcher_a, _ = make_fetcher(list(script))
        refresher.refresh(store_a, targets, fetcher_a, 1, 1, 20, log=lambda *a: None)
        fetcher_b, _ = make_fetcher(list(script))
        refresher.refresh(store_b, targets, fetcher_b, 1, 4, 20, log=lambda *a: None)
        self.assertEqual(profiles.encode(store_a, "t"), profiles.encode(store_b, "t"))


class SelectionTests(unittest.TestCase):
    def test_never_fetched_accounts_come_first_then_the_stalest(self):
        store = {
            1: profiles.new_entry(fetched=30),
            2: profiles.new_entry(fetched=0),
            3: profiles.new_entry(fetched=10),
        }
        self.assertEqual(refresher.select_targets(store, [1, 2, 3], 40, False, 10), [2, 3, 1])

    def test_accounts_checked_today_are_skipped_unless_forced(self):
        store = {1: profiles.new_entry(fetched=40), 2: profiles.new_entry(fetched=39)}
        self.assertEqual(refresher.select_targets(store, [1, 2], 40, False, 10), [2])
        self.assertEqual(refresher.select_targets(store, [1, 2], 40, True, 10), [2, 1])

    def test_the_request_cap_limits_how_many_are_selected(self):
        store = {n: profiles.new_entry(fetched=0) for n in range(10)}
        self.assertEqual(len(refresher.select_targets(store, list(range(10)), 5, False, 3)), 3)


class StoreTests(unittest.TestCase):
    def test_a_store_survives_a_round_trip(self):
        store = {
            7960265730: profiles.new_entry(name="two", hash_value=AVATAR_B, fetched=5,
                                           state=profiles.STATE_LIMITED),
            7960265729: profiles.new_entry(name="one", hash_value=AVATAR_A, fetched=4,
                                           state=profiles.STATE_PUBLIC),
        }
        document = profiles.encode(store, "2026-01-01T00:00:00Z")
        self.assertEqual(document["ids"], [7960265729, 7960265730])
        self.assertEqual(profiles.decode(document), store)

    def test_encoding_is_deterministic_regardless_of_insertion_order(self):
        forwards = {n: profiles.new_entry(name=str(n)) for n in (1, 2, 3)}
        backwards = {n: profiles.new_entry(name=str(n)) for n in (3, 2, 1)}
        self.assertEqual(profiles.encode(forwards, "t"), profiles.encode(backwards, "t"))

    def test_a_truncated_avatar_blob_is_rejected(self):
        document = profiles.encode({1: profiles.new_entry()}, "t")
        document["avatars"] = document["avatars"][:-1]
        with self.assertRaises(ValueError):
            profiles.decode(document)

    def test_an_unknown_version_is_rejected(self):
        with self.assertRaises(ValueError):
            profiles.decode({"version": 99})

    def test_avatar_urls_are_recognised_on_every_steam_cdn_hostname(self):
        for host in ("avatars.steamstatic.com", "avatars.fastly.steamstatic.com",
                     "avatars.akamai.steamstatic.com"):
            self.assertEqual(profiles.avatar_hash(f"https://{host}/{AVATAR_A}_medium.jpg"), AVATAR_A)
        for bad in ("", "not a url", "http://avatars.steamstatic.com/x_medium.jpg",
                    "javascript:alert(1)", f"https://evil.test/{AVATAR_A}_medium.jpg"):
            self.assertIsNone(profiles.avatar_hash(bad))

    def test_only_real_steamid64_values_are_accepted(self):
        self.assertEqual(profiles.suffix_of("76561197960265901"), 7960265901)
        for bad in ("", "76561197960265901 ", "7656119796026590", "8656119796026590",
                    None, 76561197960265901):
            self.assertIsNone(profiles.suffix_of(bad))


class EndToEndTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.accounts = self.root / "accounts.json"
        self.profiles = self.root / "profiles.json"
        self.accounts.write_text(json.dumps([{"steamid64": steamid(n)} for n in (1, 2)]))

    def run_refresh(self, script, argv=()):
        opener = FakeOpener(script)
        real_fetcher = refresher.Fetcher

        def fetcher(key, timeout, attempts, delay):
            return real_fetcher(key, timeout, attempts, 0.0, opener=opener, sleep=lambda _: None)

        refresher.Fetcher = fetcher
        try:
            code = refresher.main(["--accounts", str(self.accounts),
                                   "--profiles", str(self.profiles), *argv])
        finally:
            refresher.Fetcher = real_fetcher
        return code, opener

    def test_a_run_writes_a_cache_the_site_can_read(self):
        import os
        os.environ["STEAM_WEB_API_KEY"] = KEY
        code, _ = self.run_refresh([{"response": {"players": [player(1), player(2)]}}])
        self.assertEqual(code, 0)
        store = profiles.load(self.profiles)
        self.assertEqual(sorted(store), [7960265729, 7960265730])

    def test_the_api_key_never_reaches_the_generated_file(self):
        import os
        os.environ["STEAM_WEB_API_KEY"] = KEY
        self.run_refresh([{"response": {"players": [player(1), player(2)]}}])
        self.assertNotIn(KEY, self.profiles.read_text(encoding="utf-8"))

    def test_a_run_where_every_batch_fails_writes_nothing(self):
        import os
        os.environ["STEAM_WEB_API_KEY"] = KEY
        self.profiles.write_text(json.dumps(profiles.encode(
            {7960265729: profiles.new_entry(name="kept", hash_value=AVATAR_A, fetched=1)},
            "2026-01-01T00:00:00Z")))
        before = self.profiles.read_text(encoding="utf-8")
        code, _ = self.run_refresh([http_error(500)] * 8)
        self.assertEqual(code, 1)
        self.assertEqual(self.profiles.read_text(encoding="utf-8"), before)

    def test_a_changed_avatar_is_published_by_the_next_successful_run(self):
        import os
        os.environ["STEAM_WEB_API_KEY"] = KEY
        self.run_refresh([{"response": {"players": [player(1, avatar=AVATAR_A),
                                                    player(2, avatar=AVATAR_A)]}}])
        published = json.loads(self.profiles.read_text(encoding="utf-8"))
        self.assertIn(AVATAR_A, published["avatars"])
        self.assertNotIn(AVATAR_B, published["avatars"])

        # The player changed their picture; the next run picks the new hash up
        # without anyone touching the file or clearing a browser cache.
        self.run_refresh([{"response": {"players": [player(1, avatar=AVATAR_B),
                                                    player(2, avatar=AVATAR_A)]}}],
                         argv=("--force",))
        store = profiles.load(self.profiles)
        self.assertEqual(store[7960265729]["hash"], AVATAR_B)
        self.assertEqual(store[7960265730]["hash"], AVATAR_A)
        self.assertEqual(profiles.avatar_url(store[7960265729]["hash"]),
                         f"https://avatars.steamstatic.com/{AVATAR_B}_medium.jpg")

    def test_a_missing_key_is_reported_rather_than_guessed_at(self):
        import os
        os.environ.pop("STEAM_WEB_API_KEY", None)
        code, opener = self.run_refresh([])
        self.assertEqual(code, 1)
        self.assertEqual(opener.urls, [])

    def test_entries_for_removed_accounts_are_pruned(self):
        import os
        os.environ["STEAM_WEB_API_KEY"] = KEY
        self.profiles.write_text(json.dumps(profiles.encode({
            7960265729: profiles.new_entry(hash_value=AVATAR_A, fetched=99999),
            7960265730: profiles.new_entry(hash_value=AVATAR_A, fetched=99999),
            7960265999: profiles.new_entry(hash_value=AVATAR_B, fetched=99999),
        }, "2026-01-01T00:00:00Z")))
        code, _ = self.run_refresh([])
        self.assertEqual(code, 0)
        self.assertEqual(sorted(profiles.load(self.profiles)), [7960265729, 7960265730])

    def test_pruning_is_refused_when_the_account_file_shrinks_implausibly(self):
        import os
        os.environ["STEAM_WEB_API_KEY"] = KEY
        store = {7960265728 + n: profiles.new_entry(hash_value=AVATAR_A, fetched=99999)
                 for n in range(1, 21)}
        self.profiles.write_text(json.dumps(profiles.encode(store, "2026-01-01T00:00:00Z")))
        code, _ = self.run_refresh([])
        self.assertEqual(code, 0)
        self.assertEqual(len(profiles.load(self.profiles)), 20)

    def test_an_unchanged_run_does_not_rewrite_the_file(self):
        import os
        os.environ["STEAM_WEB_API_KEY"] = KEY
        self.run_refresh([{"response": {"players": [player(1), player(2)]}}])
        first = self.profiles.read_text(encoding="utf-8")
        code, _ = self.run_refresh([{"response": {"players": [player(1), player(2)]}}],
                                   argv=("--force",))
        self.assertEqual(code, 0)
        # generated_at moved on but nothing else did, so the file stayed put.
        self.assertEqual(self.profiles.read_text(encoding="utf-8"), first)


if __name__ == "__main__":
    unittest.main()
