# Pipeline scripts

These scripts build the database in `data/normalized/` and everything
generated from it: the website's JSON files and the table in `SOURCES.md`.

You only need Python 3.10 or newer. There is nothing to install and no
database to set up.

Run the tests with:

```bash
python -m unittest discover -s tests
```

## How the pieces fit together

```
  upstream ban list (a website)
        |
        |  fetch_sourcebans.py      downloads and parses it into JSON
        v
  a JSON file you can inspect
        |
        |  merge_sourcebans.py      adds it to the database
        v
  data/normalized/*.csv             <- the real data
        |
        |  recompute_confidence.py  scores every account
        |  export_site_data.py      writes docs/data/*.json for the website
        |  build_site_bundle.py     writes the compact copy the site loads
        |  generate_sources_md.py   writes the table in SOURCES.md
        v
  everything else
```

Steam persona names and avatars are on a separate track. They are not derived
from the CSVs and are not part of a database import:

```
  docs/data/accounts.json
        |
        |  refresh_steam_profiles.py   asks the Steam Web API for each account
        v
  docs/data/profiles.json              <- what the website shows for a player
```

The CSV files are the source of truth. Everything else is generated from
them, so if you change a CSV you must re-run the last four scripts.

PostgreSQL is optional. `db/init/` holds the same data as SQL for anyone
who wants to query it properly, but the pipeline never needs it.

## Adding a new SourceBans source

Most TF2 communities publish their bans through SourceBans, so this is
the usual way to add data.

**1. Find the ban list page.**

It is normally at `<site>/index.php?p=banlist`. Some communities move it
to `/bans`, `bans.<site>` or `sb.<site>`, and one of them serves it over
plain HTTP only, which cost an embarrassing amount of time to work out.
Open it in a browser first. If it asks for a login or shows a "checking
your browser" screen, these scripts cannot read it.

**2. Download it.**

```bash
python scripts/fetch_sourcebans.py \
    --url "https://bans.example.tf/index.php?p=banlist" \
    --out /tmp/example.json
```

This only downloads and parses. It does not change the database, so it is
safe to run and inspect the result.

If every page reports `0 rows`, the site uses an HTML layout that
`lib/sourcebans.py` does not recognise yet. Open the page source and find
where the SteamID appears, then add a pattern there. There are three
known layouts so far, which is three more than SourceBans documents.

If the site splits pages by an offset instead of a page number, use
`--page-param`, `--page-start` and `--page-step`. Run `--help` for details.

**3. Register the source.**

Add one row to `data/normalized/sources.csv` and one to
`source_profiles.csv`, copying an existing `sourcebans` row as a template.
Use the next unused `source_id`. Two fields need a decision:

- `independence_group`: a name unique to this community. Sources sharing a
  group never count as separate evidence for the same account, which is
  how copies and mirrors are stopped from inflating a score.
- `base_weight`: how much this community's bans are worth, normally 70 to
  90. Judge it by how carefully they moderate.

**4. Add it to the database.**

```bash
python scripts/merge_sourcebans.py --source-id 96 --records /tmp/example.json
```

Add `--dry-run` first to see what it would do without writing anything.
Running it twice is safe, because records are matched by a content hash
and duplicates are skipped.

**5. Regenerate everything derived from the CSVs.**

```bash
python scripts/recompute_confidence.py
python scripts/export_site_data.py
python scripts/build_site_bundle.py
python scripts/generate_sources_md.py
```

**6. Check the result.**

Update the snapshot line in the top-level `README.md`, then run
`git diff --stat`. Expect a few thousand added rows and a handful of
changed files. If it reports that all 36,000 accounts changed, something
went wrong, and it is usually line endings.

## Refreshing Steam profiles

`docs/data/profiles.json` holds the persona name and avatar Steam currently
serves for every account, so the website never has to ask Steam anything. The
`refresh steam profiles` workflow rebuilds it every morning from the
`STEAM_WEB_API_KEY` repository secret, and there is nothing to do by hand.

To run it locally, get a key from https://steamcommunity.com/dev/apikey:

```bash
STEAM_WEB_API_KEY=... python scripts/refresh_steam_profiles.py
```

It asks `ISteamUser/GetPlayerSummaries` for 100 accounts at a time, stalest
first, and merges what comes back. A run that fails to reach Steam leaves the
published file exactly as it was; it never blanks an avatar because a request
timed out. `--dry-run` reports what it would fetch without contacting anything.

The key is only ever read from the environment. `scripts/check_profiles.py`
fails the build if anything shaped like one turns up in the generated file.

## Looking up community bans through SteamHistory

SteamHistory aggregates the SourceBans installations of a lot of communities.
Asking it about accounts already in this database finds bans from servers that
have never been imported here, without having to locate and scrape each one.

```bash
STEAMHISTORY_API_KEY=... python scripts/fetch_steamhistory_bans.py \
    --out /tmp/steamhistory.json --max-requests 20
```

Get a key by logging into https://steamhistory.net/api with a Steam account.
The endpoint takes up to 100 SteamIDs per call, so the whole database is a few
hundred requests. `--max-requests` bounds a run and `--offset` continues one
that was interrupted.

Two things about this API are worth knowing before touching the code. It
answers **HTTP 200 even when it rejects the request**, putting the problem in
an `error` field, so the status code on its own means nothing. And it is a
lookup, not a dump: there is no documented way to ask for every SteamID it
knows about, which is why this enriches accounts you already have rather than
discovering new ones.

Like `fetch_sourcebans.py`, this only downloads and normalizes. It writes one
JSON file and changes no CSV, because the result needs a provenance decision
first:

- Each record keeps the community that issued the ban in `server`, with
  SteamHistory recorded as the route it arrived by. A ban from BlackWonder is
  evidence from BlackWonder, not from SteamHistory.
- The report groups records by community and says which ones already match a
  registered source. Those are **mirrors of data already imported** and must
  share that source's `independence_group`, or the same ban counts twice and
  inflates the score. Communities that match nothing are new evidence and need
  a source row of their own.
- Where a name matches more than one registered source, every candidate is
  listed rather than one being guessed at.

Once the lookup file exists, merge it:

```bash
python scripts/merge_steamhistory.py --records /tmp/steamhistory.json --dry-run
python scripts/merge_steamhistory.py --records /tmp/steamhistory.json
```

The merge reads `data/reference/steamhistory_servers.csv`, which records one
decision per community: `map` it onto the source it already has, `register` a
new one, or `skip` it. A community that is not in that table is reported and
left out; guessing would put bans from another game into a TF2 database, which
is how the Rust servers SteamHistory also covers would have got in.

## Adding a tf2bd-style playerlist

These are single JSON files rather than websites, so there is no fetch
script for them yet. Each one so far has been downloaded by hand and
converted individually. If a third turns up, write the fetcher.

## Updating the PostgreSQL files

`db/init/003_seed.sql` is about 44 MB of `INSERT` statements. There is
deliberately no script that rebuilds it from scratch, because doing so
would rewrite all 200,000 lines every time and produce a diff nobody is
ever going to read. Instead, append new rows to the end of each table's
existing block of `INSERT` statements.

Write a small throwaway script for the change you are making, run it, and
delete it. `db/init/001_schema.sql` lists the exact columns and
constraints each table expects.

### Always test the result against a real database

`recompute_confidence.py` is a Python copy of the SQL in
`db/init/005_confidence_views.sql`, and `account_summary.csv` mirrors a
view in `002_views.sql`. Both must agree exactly. Loading the files into a
scratch database proves the SQL is valid and that the two copies have not
drifted apart:

```bash
createdb tf2sentinel_scratch
for f in db/init/0*.sql; do
    psql -d tf2sentinel_scratch -v ON_ERROR_STOP=1 -f "$f"
done

psql -d tf2sentinel_scratch -t -A -F',' -c \
    "COPY (SELECT steamid64, confidence_score, confidence_tier
             FROM v_account_confidence ORDER BY 1) TO STDOUT WITH CSV" > /tmp/pg.csv

dropdb tf2sentinel_scratch
```

Then compare `/tmp/pg.csv` with the matching columns of
`data/normalized/confidence.csv`. They must be identical. Any difference,
even one of 0.1, means the Python and the SQL disagree and one of them is
wrong. Find out which before committing.

## What each file does

| File | Purpose | Tests |
|---|---|---|
| `lib/steamid.py` | Converts between the three SteamID formats | `tests/test_steamid.py` |
| `lib/sourcebans.py` | Reads ban-list HTML in any of its three layouts | |
| `lib/classify.py` | Decides if a ban reason means cheating | `tests/test_classify.py` |
| `lib/dateparse.py` | Reads the many date formats these sites print | `tests/test_dateparse.py` |
| `fetch_sourcebans.py` | Downloads one ban list and saves it as JSON | |
| `fetch_steamhistory_bans.py` | Looks up community bans for known accounts | `tests/test_steamhistory.py` |
| `merge_sourcebans.py` | Adds a downloaded ban list to the CSVs | |
| `recompute_confidence.py` | Scores every account | |
| `export_site_data.py` | Writes the website's JSON files | |
| `build_site_bundle.py` | Writes the compact copy of accounts.json the site loads | `tests/frontend/` |
| `refresh_steam_profiles.py` | Refreshes persona names and avatars from Steam | `tests/test_steam_profiles.py` |
| `check_profiles.py` | Checks the published profile cache is well formed | |
| `merge_steamhistory.py` | Adds looked-up community bans to the CSVs | `tests/test_merge_steamhistory.py` |
| `ingest.py` | Re-fetches the tf2bd playerlists listed in sources.csv | |
| `generate_sources_md.py` | Writes the source table in `SOURCES.md` | |
