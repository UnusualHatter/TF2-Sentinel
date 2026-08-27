'use strict';

/* Differential test: every query is answered twice, once by the search index
 * and once by a deliberately naive scan of the same text. They must agree on
 * the full committed database, or the index is wrong. */

const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');

const docs = path.join(__dirname, '..', '..', 'docs');
const data = require(path.join(docs, 'lib', 'sentinel-data.js'));
const readJson = name => JSON.parse(fs.readFileSync(path.join(docs, 'data', name), 'utf8'));

const dataset = data.decodeBundle(readJson('accounts.compact.json'));
const profiles = data.decodeProfiles(readJson('profiles.json'));
const sources = data.prepareSources(readJson('sources.json'));
const sourceLabel = slug => (sources.get(slug) ? sources.get(slug).name : slug);
const index = data.buildSearchIndex(dataset, profiles, sourceLabel);

// The oracle: rebuild each row's searchable text independently of the index.
const rowText = [];
for (let i = 0; i < dataset.count; i += 1) {
  const suffix = dataset.ids[i];
  const slot = data.profileSlot(profiles, suffix);
  const parts = [
    data.steamId64(suffix),
    data.steam3(suffix),
    dataset.names[i],
    data.profileName(profiles, slot),
    dataset.flagsFor(i).join(' '),
    dataset.slugsFor(i).map(sourceLabel).join(' ')
  ];
  rowText.push(data.normalizeText(parts.join(' ')).split('\n').join(' '));
}

function oracle(query, tier) {
  const parsed = data.parseSearch(query);
  const out = [];
  if (parsed.id >= 0) {
    for (let i = 0; i < dataset.count; i += 1) {
      if (dataset.ids[i] === parsed.id) {
        if (!tier || dataset.tiers[dataset.tier[i]] === tier) out.push(i);
        return out;
      }
    }
    if (parsed.exact) return out;
  } else if (parsed.exact) {
    return out;
  }
  for (let i = 0; i < dataset.count; i += 1) {
    if (tier && dataset.tiers[dataset.tier[i]] !== tier) continue;
    if (parsed.terms.every(t => rowText[i].indexOf(t) !== -1)) out.push(i);
  }
  return out;
}

function agree(query, tier) {
  const got = [...data.search(dataset, index, query, tier || '')];
  const want = oracle(query, tier || '');
  assert.deepEqual(got, want,
    `disagreement for ${JSON.stringify(query)}${tier ? ' tier=' + tier : ''}: ` +
    `index ${got.length} rows, oracle ${want.length} rows`);
  return got.length;
}

test('the index agrees with a naive scan on hand-picked queries', () => {
  const queries = ['', ' ', '   ', 'a', 'e', 'bot', 'cheater', 'server ban', 'sourcebans',
    'sleepy', 'blackwonder', 'dpg.tf', 'sappho', 'liquid.tf', 'pubs.tf', 'sg-gaming',
    'the', 'x', '0', '7656', 'aim', 'aimbot', 'valve', 'vac', 'ugc',
    'bot cheater', 'cheater bot', 'skial panda', 'zzzznope', 'a b c d e',
    'BLACKWONDER', 'BlackWonder', 'bLaCkWoNdEr'];
  for (const q of queries) agree(q);
});

test('the index agrees on queries taken from the data itself', () => {
  let checked = 0;
  for (let i = 0; i < dataset.count && checked < 300; i += 37) {
    const name = dataset.names[i] || data.profileName(profiles, data.profileSlot(profiles, dataset.ids[i]));
    if (!name || name.length < 3) continue;
    agree(name);
    agree(data.normalizeText(name).slice(0, 4));
    checked += 1;
  }
  assert.ok(checked >= 100, 'expected at least 100 sampled names, got ' + checked);
});

test('the index agrees on every source name', () => {
  for (const slug of dataset.slugs) {
    agree(sourceLabel(slug));
    agree(slug);
  }
});

test('the index agrees on every SteamID form for sampled accounts', () => {
  for (let i = 0; i < dataset.count; i += 2711) {
    const suffix = dataset.ids[i];
    const accountId = suffix - 7960265728;
    agree(data.steamId64(suffix));
    agree(`[U:1:${accountId}]`);
    agree(`STEAM_0:${accountId % 2}:${Math.floor(accountId / 2)}`);
    agree(`https://steamcommunity.com/profiles/${data.steamId64(suffix)}/`);
    agree(String(accountId));
  }
});

test('the index agrees when a tier filter is combined with a query', () => {
  for (const tier of dataset.tiers) {
    agree('', tier);
    agree('bot', tier);
    agree('server ban', tier);
    agree(data.steamId64(dataset.ids[100]), tier);
  }
});

test('queries with characters that mean something in a regex are literal', () => {
  for (const q of ['a.b', 'c++', '(test)', '[U:1:', '$^', '\\d+', '*', '?', '|', 'a|b',
    '.*', '[]', '{2}', 'name (2)', 'a\tb']) {
    agree(q);
  }
});

test('no search term can span two rows', () => {
  // Terms are split on whitespace and rows are separated by a newline, so a
  // single term can never reach across a row boundary. Check the property
  // rather than a result: whitespace-only input is simply an empty query.
  assert.deepEqual(data.parseSearch('\n').terms, []);
  assert.equal(data.search(dataset, index, '\n', '').length, dataset.count);

  const spanning = index.blob.slice(index.starts[1] - 4, index.starts[1] + 4);
  assert.ok(spanning.includes('\n'), 'expected the slice to cross a row boundary');
  for (const term of data.parseSearch(spanning).terms) {
    assert.ok(!term.includes('\n'), 'a term must not contain the row separator');
  }
  agree(spanning);
});

test('unicode names are found by their folded form and their own form', () => {
  let checked = 0;
  for (let slot = 0; slot < profiles.count && checked < 40; slot += 1) {
    const name = profiles.names[slot];
    if (!name || name.length < 4 || !/[^\x00-\x7f]/.test(name)) continue;
    agree(name);
    agree(data.normalizeText(name));
    checked += 1;
  }
  assert.ok(checked > 0, 'no non-ascii persona names to check');
});

test('every account in the database is reachable by its own SteamID64', () => {
  for (let i = 0; i < dataset.count; i += 997) {
    const hits = data.search(dataset, index, dataset.steamId64(i === 0 ? 0 : i), '');
    assert.equal(hits.length, 1, 'row ' + i);
    assert.equal(hits[0], i);
  }
});
