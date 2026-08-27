'use strict';

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const docs = path.join(__dirname, '..', '..', 'docs');
const data = require(path.join(docs, 'lib', 'sentinel-data.js'));

const readJson = name => JSON.parse(fs.readFileSync(path.join(docs, 'data', name), 'utf8'));

const bundleRaw = readJson('accounts.compact.json');
const profilesRaw = readJson('profiles.json');
const sourceRows = readJson('sources.json');

const dataset = data.decodeBundle(bundleRaw);
const profiles = data.decodeProfiles(profilesRaw);
const sources = data.prepareSources(sourceRows);
const sourceLabel = slug => (sources.get(slug) ? sources.get(slug).name : slug);

test('escaping neutralises every character that can break out of markup', () => {
  assert.equal(data.escapeHtml('<img src=x onerror="alert(1)">'),
    '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  assert.equal(data.escapeHtml("it's \"quoted\" & <bold>"),
    'it&#39;s &quot;quoted&quot; &amp; &lt;bold&gt;');
  assert.equal(data.escapeHtml(null), '');
  assert.equal(data.escapeHtml(undefined), '');
});

test('only plain web links survive URL validation', () => {
  assert.equal(data.safeUrl('https://example.test/a?b=c#d'), 'https://example.test/a?b=c#d');
  assert.equal(data.safeUrl('http://example.test/'), 'http://example.test/');
  for (const bad of ['javascript:alert(1)', 'JaVaScRiPt:alert(1)', ' javascript:alert(1)',
    'data:text/html,<script>', 'vbscript:x', '//example.test/', '/relative', '', null,
    'https://', 'https:///nohost']) {
    assert.equal(data.safeUrl(bad), '', 'should have rejected ' + String(bad));
  }
});

test('a source catalog entry cannot pollute Object.prototype', () => {
  const hostile = data.prepareSources([
    { slug: '__proto__', name: 'x', upstream_repo: 'https://example.test/' },
    { slug: 'constructor', name: 'y', upstream_repo: 'javascript:alert(1)' }
  ]);
  assert.equal(({}).polluted, undefined);
  assert.equal(hostile.get('__proto__').name, 'x');
  assert.equal(hostile.get('constructor').url, '');
});

test('SteamID64 conversion round-trips and rejects anything else', () => {
  assert.equal(data.steamId64(7960265901), '76561197960265901');
  assert.equal(data.suffixOf('76561197960265901'), 7960265901);
  assert.equal(data.steam3(7960265901), '[U:1:173]');
  for (const bad of ['', '7656119796026590', '86561197960265901', '76561197960265901x', 'abc']) {
    assert.equal(data.suffixOf(bad), -1);
  }
});

test('the compact bundle describes the same accounts as accounts.json', () => {
  const accounts = readJson('accounts.json');
  assert.equal(dataset.count, accounts.length);

  const splitList = value => [...new Set(String(value || '').split(';').filter(Boolean))];
  const step = Math.max(1, Math.floor(accounts.length / 500));
  for (let i = 0; i < accounts.length; i += step) {
    const row = accounts[i];
    assert.equal(dataset.steamId64(i), row.steamid64);
    assert.equal(dataset.steam3(i), row.steam3);
    assert.equal(dataset.names[i], row.latest_name);
    assert.equal(dataset.tiers[dataset.tier[i]], row.confidence_tier);
    assert.equal(dataset.scores[dataset.score[i]], row.confidence_score);
    assert.equal(dataset.groups[i], row.independent_source_groups);
    assert.equal(dataset.evidence[i], row.evidence_count);
    assert.deepEqual(dataset.flagsFor(i), splitList(row.flags));
    assert.equal(dataset.primarySlug(i), row.primary_source);

    const all = splitList(row.all_sources);
    const strongest = splitList(row.strongest_sources).filter(s => all.includes(s));
    const ordered = strongest.concat(all.filter(s => !strongest.includes(s)));
    assert.deepEqual(dataset.slugsFor(i), ordered);
  }
});

test('the fallback path produces the same view as the bundle', () => {
  const sample = readJson('accounts.json').slice(0, 400);
  const fallback = data.datasetFromAccounts(sample);
  assert.equal(fallback.count, sample.length);
  for (let i = 0; i < sample.length; i += 1) {
    assert.equal(fallback.steamId64(i), dataset.steamId64(i));
    assert.deepEqual(fallback.slugsFor(i), dataset.slugsFor(i));
    assert.equal(fallback.tiers[fallback.tier[i]], dataset.tiers[dataset.tier[i]]);
    assert.equal(fallback.scores[fallback.score[i]], dataset.scores[dataset.score[i]]);
  }
});

test('a malformed bundle is rejected instead of rendering nonsense', () => {
  assert.throws(() => data.decodeBundle(null), /unsupported/);
  assert.throws(() => data.decodeBundle({ version: 2 }), /unsupported/);
  assert.throws(() => data.decodeBundle({ version: 1 }), /ids/);
  assert.throws(() => data.decodeBundle({ version: 1, ids: [1, 2], names: ['a'] }), /names/);
});

test('profile lookup finds every published entry and misses cleanly', () => {
  assert.ok(profiles.count > 0);
  for (const at of [0, 1, Math.floor(profiles.count / 2), profiles.count - 1]) {
    assert.equal(data.profileSlot(profiles, profiles.ids[at]), at);
  }
  assert.equal(data.profileSlot(profiles, 1), -1);
  assert.equal(data.profileName(profiles, -1), '');
  assert.equal(data.profileAvatarUrl(profiles, -1), '');
});

test('avatar URLs are built only from a real hash', () => {
  const fake = data.decodeProfiles({
    version: 1, ids: [1, 2, 3], names: ['a', 'b', 'c'],
    avatars: 'a'.repeat(40) + '0'.repeat(40) + 'Z'.repeat(40),
    fetched: [0, 0, 0], state: [1, 1, 1],
    avatar_base: 'https://avatars.steamstatic.com/', avatar_size: '_medium.jpg', hash_length: 40
  });
  assert.equal(data.profileAvatarUrl(fake, 0),
    'https://avatars.steamstatic.com/' + 'a'.repeat(40) + '_medium.jpg');
  assert.equal(data.profileAvatarUrl(fake, 1), '', 'the all-zero hash means no avatar');
  assert.equal(data.profileAvatarUrl(fake, 2), '', 'a non-hex hash is refused');
});

test('a profile file that does not match its own header is discarded', () => {
  assert.equal(data.decodeProfiles({ version: 1, ids: [1, 2], avatars: 'a'.repeat(40) }).count, 0);
  assert.equal(data.decodeProfiles({ version: 9 }).count, 0);
  assert.equal(data.decodeProfiles(null).count, 0);
});

test('every published avatar hash produces a Steam CDN URL', () => {
  const allowed = /^https:\/\/avatars\.steamstatic\.com\/[0-9a-f]{40}_medium\.jpg$/;
  let built = 0;
  for (let slot = 0; slot < profiles.count; slot += 1) {
    const url = data.profileAvatarUrl(profiles, slot);
    if (!url) continue;
    built += 1;
    assert.match(url, allowed);
  }
  assert.ok(built > 0);
});

test('an exact SteamID64 finds its account without the search index', () => {
  const wanted = dataset.steamId64(dataset.count - 7);
  const hits = data.search(dataset, null, wanted.toLowerCase(), '');
  assert.equal(hits.length, 1);
  assert.equal(dataset.steamId64(hits[0]), wanted);
  assert.equal(data.search(dataset, null, '76561190000000000', '').length, 0);
});

test('text search returns matching rows in database order', () => {
  const index = data.buildSearchIndex(dataset, profiles, sourceLabel);
  const slug = dataset.slugs[0];
  const label = sourceLabel(slug).toLowerCase();
  const hits = data.search(dataset, index, label, '');
  assert.ok(hits.length > 0);
  for (let i = 1; i < hits.length; i += 1) assert.ok(hits[i] > hits[i - 1]);
  for (const row of hits) {
    const text = index.blob.slice(index.starts[row], index.starts[row + 1] - 1);
    assert.ok(text.includes(label));
  }
  assert.equal(data.search(dataset, index, 'zzzzznotinthedatabasezzzzz', '').length, 0);
});

test('search matches a persona name that only the profile cache knows', () => {
  const index = data.buildSearchIndex(dataset, profiles, sourceLabel);
  let checked = 0;
  for (let slot = 0; slot < profiles.count && checked < 5; slot += 1) {
    const name = profiles.names[slot];
    if (!name || name.length < 6 || !/^[a-z0-9 ]+$/i.test(name)) continue;
    const hits = data.search(dataset, index, name.toLowerCase(), '');
    assert.ok(hits.length > 0, 'expected a hit for persona ' + JSON.stringify(name));
    checked += 1;
  }
  assert.equal(checked, 5);
});

test('the tier filter narrows results and rejects unknown tiers', () => {
  const index = data.buildSearchIndex(dataset, profiles, sourceLabel);
  const tier = dataset.tiers[dataset.tier[0]];
  const filtered = data.search(dataset, index, '', tier);
  assert.ok(filtered.length > 0);
  assert.ok(filtered.length < dataset.count);
  for (const row of filtered) assert.equal(dataset.tiers[dataset.tier[row]], tier);
  assert.equal(data.search(dataset, index, '', 'no_such_tier').length, 0);

  const everything = data.search(dataset, index, '', '');
  assert.equal(everything.length, dataset.count);
});

test('row offsets map back to the right row everywhere in the blob', () => {
  const index = data.buildSearchIndex(dataset, profiles, sourceLabel);
  for (const row of [0, 1, 17, Math.floor(dataset.count / 2), dataset.count - 1]) {
    assert.equal(data.rowAtOffset(index.starts, index.starts[row]), row);
    assert.equal(data.rowAtOffset(index.starts, index.starts[row + 1] - 1), row);
  }
});

test('badges cope with source types the catalog has not used yet', () => {
  assert.equal(data.sourceBadge({ slug: 'valve-vac-ban' }), 'VAC');
  assert.equal(data.sourceBadge({ source_type: 'sourcebans' }), 'Server ban');
  assert.equal(data.sourceBadge({ source_type: 'something_invented_next_year' }), 'Source');
  assert.equal(data.sourceBadge(null), 'Source');
  assert.equal(data.tierLabel('very_high'), 'Very high');
  assert.equal(data.tierLabel(''), 'Unscored');
});

test('every source slug the database refers to resolves in the catalog', () => {
  const missing = new Set();
  for (const slug of dataset.slugs) if (!sources.has(slug)) missing.add(slug);
  assert.deepEqual([...missing], []);
});

test('a bundle with an unusable account id is refused', () => {
  const base = { version: 1, names: [''], tier: [0], score: [0], groups: [0], evidence: [0],
    flags: [0], primary: [-1], sources: [0], tiers: ['low'], scores: ['1'], slugs: ['s'],
    source_sets: [[0]], flag_sets: [[]] };
  for (const bad of [['7960265901'], [-1], [1.5], [1e21], [null]]) {
    assert.throws(() => data.decodeBundle({ ...base, ids: bad }), /unusable account id/,
      'should have refused ' + JSON.stringify(bad));
  }
  assert.equal(data.decodeBundle({ ...base, ids: [7960265901] }).steamId64(0), '76561197960265901');
});

test('every way of writing a SteamID reaches the same account', () => {
  const suffix = 7960265901;
  const steamid64 = data.steamId64(suffix);
  const accountId = suffix - 7960265728;
  const forms = [
    steamid64,
    '  ' + steamid64 + ' ',
    `STEAM_0:${accountId % 2}:${Math.floor(accountId / 2)}`,
    `steam_1:${accountId % 2}:${Math.floor(accountId / 2)}`,
    `[U:1:${accountId}]`,
    `U:1:${accountId}`,
    `u:1:${accountId}`,
    `https://steamcommunity.com/profiles/${steamid64}/`,
    `http://steamcommunity.com/profiles/${steamid64}`,
    `steamcommunity.com/profiles/${steamid64}`,
    `https://www.steamcommunity.com/profiles/${steamid64}?snr=1`,
    `https://steamhistory.net/id/${steamid64}`,
    String(accountId)
  ];
  for (const form of forms) {
    assert.equal(data.parseSearch(form).id, suffix, 'failed to parse ' + form);
  }
});

test('an identifier query is answered without the text index', () => {
  const row = 4321;
  const suffix = dataset.ids[row];
  const accountId = suffix - 7960265728;
  for (const form of [dataset.steamId64(row), `[U:1:${accountId}]`,
    `STEAM_0:${accountId % 2}:${Math.floor(accountId / 2)}`,
    `https://steamcommunity.com/profiles/${dataset.steamId64(row)}`]) {
    const hits = data.search(dataset, null, form, '');
    assert.equal(hits.length, 1, 'no hit for ' + form);
    assert.equal(hits[0], row);
  }
});

test('an identifier that is not in the database returns nothing, not a guess', () => {
  assert.equal(data.search(dataset, null, '76561190000000000', '').length, 0);
  assert.equal(data.search(dataset, null, 'https://steamcommunity.com/profiles/76561190000000000', '').length, 0);
  assert.equal(data.search(dataset, null, 'STEAM_0:0:1', '').length, 0);
});

test('a vanity profile link falls back to searching for the name', () => {
  const parsed = data.parseSearch('https://steamcommunity.com/id/Some%20Player/');
  assert.equal(parsed.id, -1);
  assert.equal(parsed.exact, false);
  assert.deepEqual(parsed.terms, ['some', 'player']);
});

test('a bare number that is not an account still searches the text', () => {
  const index = data.buildSearchIndex(dataset, profiles, sourceLabel);
  const parsed = data.parseSearch('9999999999');
  assert.equal(parsed.exact, false);
  assert.deepEqual(parsed.terms, ['9999999999']);
  assert.equal(data.search(dataset, index, '9999999999', '').length, 0);
});

test('several words all have to match, in any order', () => {
  const index = data.buildSearchIndex(dataset, profiles, sourceLabel);
  const words = sourceLabel(dataset.slugs[0]).toLowerCase().split(/[^a-z0-9]+/).filter(w => w.length > 3);
  assert.ok(words.length >= 2, 'need a two-word source name for this check');
  const both = data.search(dataset, index, words[0] + ' ' + words[1], '');
  const reversed = data.search(dataset, index, words[1] + ' ' + words[0], '');
  const single = data.search(dataset, index, words[0], '');
  assert.deepEqual([...both], [...reversed]);
  assert.ok(both.length > 0);
  assert.ok(both.length <= single.length);
  assert.equal(data.search(dataset, index, words[0] + ' zzzznotherezzzz', '').length, 0);
});

test('accents in a name do not have to be typed to find it', () => {
  assert.equal(data.normalizeText('Café ÜBER Ñoño'), 'cafe uber nono');
  const index = data.buildSearchIndex(dataset, profiles, sourceLabel);
  let checked = 0;
  for (let slot = 0; slot < profiles.count && checked < 3; slot += 1) {
    const name = profiles.names[slot];
    if (!name || !/[À-ɏ]/.test(name)) continue;
    const folded = data.normalizeText(name);
    if (folded === name.toLowerCase() || /\s/.test(folded)) continue;
    assert.ok(data.search(dataset, index, folded, '').length > 0,
      'expected a hit for folded persona ' + JSON.stringify(name));
    checked += 1;
  }
  assert.ok(checked > 0, 'no accented persona names in the cache to check');
});

test('the tier filter still applies to an identifier query', () => {
  const row = 4321;
  const tier = dataset.tiers[dataset.tier[row]];
  const other = dataset.tiers.find(t => t !== tier);
  assert.equal(data.search(dataset, null, dataset.steamId64(row), tier).length, 1);
  assert.equal(data.search(dataset, null, dataset.steamId64(row), other).length, 0);
});

test('results come back strongest first, whatever the query', () => {
  const index = data.buildSearchIndex(dataset, profiles, sourceLabel);
  const cases = [['', ''], ['', 'very_high'], ['', 'medium'], ['', 'unscored'],
    ['sourcebans', ''], ['bot', 'high'], ['server ban', '']];
  for (const [query, tier] of cases) {
    const rows = data.sortByConfidence(dataset, data.search(dataset, index, query, tier));
    for (let i = 1; i < rows.length; i += 1) {
      assert.ok(dataset.scoreOf(rows[i]) <= dataset.scoreOf(rows[i - 1]),
        `out of order for ${JSON.stringify(query)}/${tier} at ${i}`);
    }
    if (tier) {
      for (const row of rows) assert.equal(dataset.tiers[dataset.tier[row]], tier);
    }
  }
});

test('sorting keeps exactly the rows it was given', () => {
  const index = data.buildSearchIndex(dataset, profiles, sourceLabel);
  const matched = data.search(dataset, index, 'sourcebans', '');
  const sorted = data.sortByConfidence(dataset, matched);
  assert.equal(sorted.length, matched.length);
  assert.deepEqual([...sorted].sort((a, b) => a - b), [...matched].sort((a, b) => a - b));
});

test('sorting does not disturb what it was handed', () => {
  const matched = data.search(dataset, null, '', 'very_high');
  const copy = [...matched];
  data.sortByConfidence(dataset, matched);
  assert.deepEqual([...matched], copy, 'the caller\'s array must be left alone');
});

test('accounts on the same score keep a stable order', () => {
  const rows = data.sortByConfidence(dataset, data.search(dataset, null, '', ''));
  const again = data.sortByConfidence(dataset, data.search(dataset, null, '', ''));
  assert.deepEqual([...rows], [...again]);
  for (let i = 1; i < rows.length; i += 1) {
    if (dataset.scoreOf(rows[i]) === dataset.scoreOf(rows[i - 1])) {
      assert.ok(rows[i] > rows[i - 1], 'ties must fall back to database order');
    }
  }
});

test('the owner annotation is not read as a cheating signal', () => {
  const owner = dataset.slugs.indexOf('tf2-sentinel-project');
  if (owner < 0) return;
  let found = 0;
  for (let i = 0; i < dataset.count; i += 1) {
    if (dataset.flagsFor(i).indexOf('owner') === -1) continue;
    found += 1;
    assert.equal(dataset.scores[dataset.score[i]], '0.0');
    assert.equal(dataset.tiers[dataset.tier[i]], 'unscored');
  }
  assert.ok(found > 0, 'expected at least one account carrying the owner flag');
});
