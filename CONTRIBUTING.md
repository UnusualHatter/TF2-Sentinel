# Contributing

## Reporting a wrong entry

If an account is listed incorrectly, the most useful place to fix it is
the original source, because every other tool reading that source is
wrong in the same way. `SOURCES.md` lists where each one came from.

You can also open an issue here. Please include the SteamID64 and which
source you think is wrong. To find that, look the account up in
`docs/data/accounts.json` and match its `all_sources` values against
`docs/data/sources.json`.

## Suggesting a new source

Open an issue with a link and a couple of example entries. Helpful things
to say:

- Is it a SourceBans site, a tf2bd-style `playerlist.json`, or something else?
- Roughly how many entries does it have?
- Are the ban reasons specific enough to tell actual cheating apart from
  conduct bans? `SOURCES.md` explains why that distinction matters.

To add it yourself, follow `scripts/README.md`. For a normal SourceBans
site it is about four commands and two new rows in a CSV.

## Working on the scripts

Please keep to the Python standard library. If something seems to need a
package from PyPI, it is worth checking whether it really does.

Run the tests before opening a pull request:

```bash
python -m unittest discover -s tests
node --test tests/frontend/*.test.js
```

If you changed anything under `docs/`, it is worth driving the real page as
well. This serves the site and checks it in a headless browser, and skips
quietly if you have neither Firefox nor Chromium installed:

```bash
python tests/browser/run_browser_test.py
```

Player names come from ban lists and from Steam, so they are hostile input.
This serves the site with persona names crafted to break out of the markup and
checks that none of them can:

```bash
python tests/browser/run_browser_test.py --poison --assertions tests/browser/xss.js
```

If you are changing how the site loads or searches, `tests/frontend/benchmark.js`
reports parse, index and query timings against the committed database:

```bash
node --expose-gc tests/frontend/benchmark.js
```

`lib/classify.py` and `lib/sourcebans.py` are the two places most likely
to be wrong. One tries to work out what a ban reason means when that
reason is sometimes the single character `.`, and the other reads HTML
that communities have been editing by hand since about 2013. Both will
misfire. If you are fixing a specific case, add it to the tests too, so
it stays fixed.

If you change anything in `db/init/`, load it into a real PostgreSQL
database first and confirm the results still match the CSVs. The steps are
in `scripts/README.md`. A `.sql` file that does not load is worse than one
that was never touched.

## What belongs here

This project stores public game identifiers and public moderation records
only. No private personal information and no doxxing material, whatever
the source. Pull requests adding either will be closed.
