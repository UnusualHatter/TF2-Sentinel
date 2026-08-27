#!/usr/bin/env python3
"""Load the real site in a real browser and check that it works.

Serves docs/ over HTTP, opens a headless browser on a copy of index.html with
tests/browser/assertions.js appended, and waits for the page to post its
results back. Everything the page asks for is served from disk, so a request
to anywhere else is visible in the report.

    python3 tests/browser/run_browser_test.py [--browser firefox]

Skips with exit code 0 if no browser is installed, so it can sit in a test
suite without demanding one.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = ROOT / "docs"
ASSERTIONS = Path(__file__).resolve().parent / "assertions.js"

# Records what the page asks the network for. Installed before anything else on
# the page runs, so nothing can slip a request past it.
RECORDER = """<script>
window.__requests = [];
(function () {
  var realFetch = window.fetch;
  window.fetch = function (input) {
    var url = typeof input === 'string' ? input : (input && input.url) || String(input);
    window.__requests.push(new URL(url, location.href).href);
    return realFetch.apply(this, arguments);
  };
  var realOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {
    window.__requests.push(new URL(url, location.href).href);
    return realOpen.apply(this, arguments);
  };
  var realImage = window.Image;
  window.Image = function () {
    var img = new realImage();
    Object.defineProperty(img, 'src', {
      set: function (value) {
        window.__requests.push(new URL(value, location.href).href);
        img.setAttribute('src', value);
      },
      get: function () { return img.getAttribute('src'); }
    });
    return img;
  };
}());
</script>
"""

BROWSERS = {
    "firefox": lambda binary, url, profile: [
        binary, "--headless", "--no-remote", "--profile", profile, url],
    "chromium": lambda binary, url, profile: [
        binary, "--headless=new", "--disable-gpu", "--no-sandbox",
        f"--user-data-dir={profile}", url],
}
BINARIES = {
    "firefox": ["firefox", "firefox-esr"],
    "chromium": ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable"],
}


class Harness(ThreadingHTTPServer):
    daemon_threads = True
    payload: dict | None = None
    served: list[str]
    assertions: Path
    poison: bool = False


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS), **kwargs)

    def log_message(self, *args):
        pass

    def do_GET(self):  # noqa: N802
        self.server.served.append(self.path)
        if self.path == "/harness.html":
            html = (DOCS / "index.html").read_text(encoding="utf-8")
            html = html.replace("<head>", "<head>\n" + RECORDER, 1)
            html = html.replace("</body>", '<script src="/__assertions__.js"></script>\n</body>', 1)
            return self._send(html.encode("utf-8"), "text/html; charset=utf-8")
        if self.path == "/__assertions__.js":
            return self._send(self.server.assertions.read_bytes(), "text/javascript; charset=utf-8")
        if self.server.poison and self.path == "/data/profiles.json":
            return self._send(poisoned_profiles(), "application/json; charset=utf-8")
        return super().do_GET()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length)
        try:
            self.server.payload = json.loads(body.decode("utf-8"))
        except ValueError:
            self.server.payload = {"results": [{"name": "results posted as JSON", "ok": False,
                                                "detail": body[:200].decode("utf-8", "replace")}]}
        self._send(b"ok", "text/plain")

    def _send(self, body: bytes, content_type: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# Persona names are whatever a player typed into Steam. These are the shapes
# that break a page that builds its markup by concatenating strings.
XSS_PAYLOADS = [
    '<script>window.__xss=1</script>',
    '<img src=x onerror="window.__xss=2">',
    '" onmouseover="window.__xss=3" x="',
    "' onfocus='window.__xss=4' autofocus='",
    '<svg/onload=window.__xss=5>',
    '</td></tr><tr><td>injected',
    'javascript:window.__xss=6',
    '<a href="javascript:window.__xss=7">link</a>',
    '&lt;script&gt;window.__xss=8&lt;/script&gt;',
    '<iframe src="javascript:window.__xss=9"></iframe>',
]


def poisoned_profiles() -> bytes:
    """The published profile cache with every persona name replaced by a payload.

    Every name rather than the first few: the table is ordered by confidence,
    so poisoning entries by their position in the cache would put them on a
    page the test never looks at.
    """
    raw = json.loads((DOCS / "data" / "profiles.json").read_text(encoding="utf-8"))
    names = raw.get("names") or []
    raw["names"] = [XSS_PAYLOADS[i % len(XSS_PAYLOADS)] for i in range(len(names))]
    return json.dumps(raw, ensure_ascii=False).encode("utf-8")


def find_browser(preferred: str | None) -> tuple[str, str] | None:
    names = [preferred] if preferred else list(BROWSERS)
    for name in names:
        for binary in BINARIES.get(name, []):
            found = shutil.which(binary)
            if found:
                return name, found
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--browser", choices=sorted(BROWSERS))
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--assertions", type=Path, default=ASSERTIONS,
                        help="alternative assertion script to run against the page")
    parser.add_argument("--poison", action="store_true",
                        help="serve persona names crafted to break out of the markup")
    parser.add_argument("--require-browser", action="store_true",
                        help="fail instead of skipping when no browser is installed")
    args = parser.parse_args()

    found = find_browser(args.browser)
    if not found:
        message = "no supported browser found; skipping the browser test"
        print(message, file=sys.stderr)
        return 1 if args.require_browser else 0
    kind, binary = found

    server = Harness(("127.0.0.1", 0), Handler)
    server.served = []
    server.assertions = args.assertions
    server.poison = args.poison
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/harness.html"
    print(f"serving {DOCS} · {kind} · {url}")

    with tempfile.TemporaryDirectory() as profile:
        command = BROWSERS[kind](binary, url, profile)
        browser = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + args.timeout
        try:
            while server.payload is None and time.monotonic() < deadline:
                if browser.poll() is not None and server.payload is None:
                    time.sleep(1)
                    break
                time.sleep(0.2)
        finally:
            browser.terminate()
            try:
                browser.wait(timeout=10)
            except subprocess.TimeoutExpired:
                browser.kill()
    server.shutdown()

    if server.payload is None:
        print("the page never reported back", file=sys.stderr)
        print("requests the server saw: " + ", ".join(server.served), file=sys.stderr)
        return 1

    results = server.payload.get("results") or []
    failed = [r for r in results if not r.get("ok")]
    for result in results:
        mark = "ok  " if result.get("ok") else "FAIL"
        detail = f"  ({result['detail']})" if result.get("detail") else ""
        print(f"{mark} {result['name']}{detail}")
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    print("requests the page made: " + ", ".join(server.payload.get("requests") or []))
    return 1 if failed or not results else 0


if __name__ == "__main__":
    raise SystemExit(main())
