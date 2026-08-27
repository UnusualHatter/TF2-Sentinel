/* Compares the startup cost of the compact bundle with reading accounts.json
 * the way the page used to. Not part of the test run:
 *
 *     node --expose-gc tests/frontend/benchmark.js
 */
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const docs = path.join(__dirname, '..', '..', 'docs');
const data = require(path.join(docs, 'lib', 'sentinel-data.js'));
const file = name => path.join(docs, 'data', name);

const mb = bytes => (bytes / 1e6).toFixed(2) + ' MB';
const ms = value => value.toFixed(1) + ' ms';

function heap() {
  if (global.gc) global.gc();
  return process.memoryUsage().heapUsed;
}

function timed(label, fn) {
  const before = heap();
  const start = process.hrtime.bigint();
  const value = fn();
  const took = Number(process.hrtime.bigint() - start) / 1e6;
  const grew = heap() - before;
  console.log(`  ${label.padEnd(38)} ${ms(took).padStart(10)}   heap ${mb(grew).padStart(9)}`);
  return { value, took, grew };
}

console.log('files');
for (const name of ['accounts.json', 'accounts.compact.json', 'profiles.json',
  'sources.json', 'meta.json']) {
  const raw = fs.readFileSync(file(name));
  console.log(`  ${name.padEnd(24)} ${mb(raw.length).padStart(9)}   gzip `
    + mb(zlib.gzipSync(raw, { level: 9 }).length).padStart(9));
}

const accountsText = fs.readFileSync(file('accounts.json'), 'utf8');
const bundleText = fs.readFileSync(file('accounts.compact.json'), 'utf8');
const profilesText = fs.readFileSync(file('profiles.json'), 'utf8');
const sourceRows = JSON.parse(fs.readFileSync(file('sources.json'), 'utf8'));
const sources = data.prepareSources(sourceRows);
const sourceLabel = slug => (sources.get(slug) ? sources.get(slug).name : slug);

console.log('\nbefore: accounts.json, with a search string built for every account');
const before = (() => {
  const parsed = timed('JSON.parse(accounts.json)', () => JSON.parse(accountsText));
  const rows = parsed.value;
  const indexed = timed('build _search for every row', () => {
    for (const row of rows) {
      const names = String(row.all_sources || '').split(';').filter(Boolean)
        .map(slug => sourceLabel(slug));
      row._search = [row.steamid64, row.steam3, row.latest_name, row.steam_persona_name,
        row.flags, ...names].filter(Boolean).join(' ').toLowerCase();
    }
    return rows;
  });
  const mapped = timed('Map by steamid64', () => new Map(rows.map(r => [r.steamid64, r])));
  return { rows, total: parsed.took + indexed.took + mapped.took,
    grew: parsed.grew + indexed.grew + mapped.grew };
})();
console.log(`  ${'total before first render'.padEnd(38)} ${ms(before.total).padStart(10)}`
  + `   heap ${mb(before.grew).padStart(9)}`);

console.log('\nafter: compact bundle, search index deferred to idle time');
const after = (() => {
  const parsed = timed('JSON.parse(accounts.compact.json)', () => JSON.parse(bundleText));
  const dataset = timed('decode into columns', () => data.decodeBundle(parsed.value));
  const parsedProfiles = timed('JSON.parse(profiles.json)', () => JSON.parse(profilesText));
  const profiles = timed('decode profiles', () => data.decodeProfiles(parsedProfiles.value));
  const critical = parsed.took + dataset.took;
  console.log(`  ${'total before first render'.padEnd(38)} ${ms(critical).padStart(10)}`
    + `   heap ${mb(parsed.grew + dataset.grew).padStart(9)}`);
  const index = timed('build the search index (idle)', () =>
    data.buildSearchIndex(dataset.value, profiles.value, sourceLabel));
  return { dataset: dataset.value, profiles: profiles.value, index: index.value, critical };
})();

console.log('\nfiltering ' + after.dataset.count.toLocaleString() + ' accounts');
const needle = 'sourcebans';
timed('before: filter() over 36k strings', () => {
  let hits = 0;
  for (const row of before.rows) if (row._search.includes(needle)) hits += 1;
  return hits;
});
timed('after: indexOf over one blob', () =>
  data.search(after.dataset, after.index, needle, ''));
timed('after: exact SteamID64 lookup', () =>
  data.search(after.dataset, after.index, after.dataset.steamId64(30000), ''));
timed('after: tier filter, no query', () =>
  data.search(after.dataset, after.index, '', 'very_high'));

console.log('\nrendering');
const page = data.search(after.dataset, after.index, '', '').subarray(0, 50);
timed('50 profile lookups', () => {
  let found = 0;
  for (const row of page) {
    if (data.profileAvatarUrl(after.profiles, data.profileSlot(after.profiles, after.dataset.ids[row]))) {
      found += 1;
    }
  }
  return found;
});
