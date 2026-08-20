"""Date parsing, including the formats each live source actually prints.

Run with: python -m unittest discover -s tests
"""

import os
import subprocess
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

from lib.dateparse import parse_to_iso  # noqa: E402


class TestKnownSourceFormats(unittest.TestCase):
    def test_each_skin_format(self):
        cases = [
            ("August 19, 2026, 10:27 pm", "2026-08-19T22:27:00Z"),   # The Furry Pound
            ("2026-08-19 00:18:36", "2026-08-19T00:18:36Z"),         # Disc-FF, UGC-Gaming
            ("Aug-19-2026 20:41:24", "2026-08-19T20:41:24Z"),        # Otaku Gaming
            ("2026-07-20T23:46:03+02:00", "2026-07-20T21:46:03Z"),   # TF2 Casual Fun
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(parse_to_iso(text), expected)

    def test_offsets_are_converted_not_dropped(self):
        self.assertEqual(parse_to_iso("2026-07-20T23:46:03+02:00"), "2026-07-20T21:46:03Z")
        self.assertEqual(parse_to_iso("2026-07-20T20:46:03-03:00"), "2026-07-20T23:46:03Z")


class TestEmptyValues(unittest.TestCase):
    def test_placeholders_and_blanks(self):
        for text in [None, "", "   ", "Not applicable", "never", "N/A"]:
            with self.subTest(text=text):
                self.assertIsNone(parse_to_iso(text))

    def test_unparseable_text(self):
        self.assertIsNone(parse_to_iso("sometime last Tuesday"))


class TestTimezoneIndependence(unittest.TestCase):
    """A naive timestamp must not be read as the scraping machine's local time.

    Regression test: it previously was, so re-running a sync in a different
    timezone silently rewrote every observed_at it had already imported.
    """

    def test_same_result_under_different_local_timezones(self):
        script = (
            "import sys; sys.path.insert(0, %r)\n"
            "from lib.dateparse import parse_to_iso\n"
            "print(parse_to_iso('2026-08-19 00:18:36'))\n" % str(SCRIPTS)
        )
        results = set()
        for tz in ["UTC", "America/Sao_Paulo", "Asia/Tokyo", "US/Hawaii"]:
            env = dict(os.environ, TZ=tz)
            out = subprocess.run(
                [sys.executable, "-c", script], env=env, capture_output=True, text=True, check=True
            )
            results.add(out.stdout.strip())
        self.assertEqual(results, {"2026-08-19T00:18:36Z"})


if __name__ == "__main__":
    unittest.main()
