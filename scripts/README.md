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
        |  generate_sources_md.py   writes the table in SOURCES.md
        v
  everything else
```

The CSV files are the source of truth. Everything else is generated from
them, so if you change a CSV you must re-run the last three scripts.

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
python scripts/generate_sources_md.py
```

**6. Check the result.**

Update the snapshot line in the top-level `README.md`, then run
`git diff --stat`. Expect a few thousand added rows and a handful of
changed files. If it reports that all 36,000 accounts changed, something
went wrong, and it is usually line endings.

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
| `merge_sourcebans.py` | Adds a downloaded ban list to the CSVs | |
| `recompute_confidence.py` | Scores every account | |
| `export_site_data.py` | Writes the website's JSON files | |
| `generate_sources_md.py` | Writes the source table in `SOURCES.md` | |
