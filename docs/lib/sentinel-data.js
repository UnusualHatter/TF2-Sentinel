/* Decoding, indexing and searching for the TF2 Sentinel database.
 *
 * Nothing here touches the DOM, so it can be exercised directly from Node as
 * well as from the page. docs/app.js is the only file that renders.
 */
'use strict';

var SentinelData = (function () {
  var ID_PREFIX = '7656119';
  var STEAM3_BASE = 7960265728; // 76561197960265728 minus the shared prefix
  var HASH_RE = /^[0-9a-f]{40}$/;
  var NO_AVATAR = '0000000000000000000000000000000000000000';
  var FIELD_SEPARATOR = '\u001f'; // never appears in a name or a slug
  var ROW_SEPARATOR = '\n';

  var ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

  function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value)
      .replace(/[&<>"']/g, function (char) { return ESCAPES[char]; });
  }

  // Source URLs come from the published catalog, which is assembled from
  // upstream data. Anything that is not a plain web link is dropped rather
  // than escaped, so a "javascript:" value can never reach an href.
  function safeUrl(value) {
    var text = String(value === null || value === undefined ? '' : value).trim();
    if (!text) return '';
    if (/^https?:\/\/[^\s/?#]/i.test(text)) return text;
    return '';
  }

  function steamId64(suffix) {
    var digits = String(suffix);
    while (digits.length < 10) digits = '0' + digits;
    return ID_PREFIX + digits;
  }

  function steam3(suffix) {
    return '[U:1:' + (suffix - STEAM3_BASE) + ']';
  }

  function suffixOf(steamid64) {
    return /^7656119\d{10}$/.test(steamid64) ? Number(steamid64.slice(ID_PREFIX.length)) : -1;
  }

  function toInt32Array(values) {
    var out = new Int32Array(values.length);
    for (var i = 0; i < values.length; i += 1) out[i] = values[i];
    return out;
  }

  function toFloat64Array(values) {
    var out = new Float64Array(values.length);
    for (var i = 0; i < values.length; i += 1) out[i] = values[i];
    return out;
  }

  // steamId64() output is interpolated straight into hrefs and attributes, so
  // the ids it is built from have to be plain ten-digit integers. Checking here
  // is what lets the renderer treat that string as safe.
  function toIdArray(values) {
    var out = new Float64Array(values.length);
    for (var i = 0; i < values.length; i += 1) {
      var value = values[i];
      if (typeof value !== 'number' || !Number.isInteger(value) || value < 0 || value > 9999999999) {
        throw new Error('accounts bundle has an unusable account id at ' + i);
      }
      out[i] = value;
    }
    return out;
  }

  function requireArray(raw, key) {
    var value = raw[key];
    if (!Array.isArray(value)) throw new Error('accounts bundle is missing "' + key + '"');
    return value;
  }

  /* ---- dataset -------------------------------------------------------- */

  function makeDataset(fields) {
    // The published score is a string so it displays exactly as generated;
    // ordering needs the number, and there are only a couple of hundred
    // distinct ones, so they are converted once rather than per comparison.
    fields.scoreValues = fields.scores.map(function (value) {
      var number = parseFloat(value);
      return isNaN(number) ? 0 : number;
    });
    fields.scoreOf = function (row) { return fields.scoreValues[fields.score[row]]; };
    fields.steamId64 = function (row) { return steamId64(fields.ids[row]); };
    fields.steam3 = function (row) { return steam3(fields.ids[row]); };
    fields.slugsFor = function (row) {
      var set = fields.sourceSets[fields.sources[row]];
      var out = new Array(set.length);
      for (var i = 0; i < set.length; i += 1) out[i] = fields.slugs[set[i]];
      return out;
    };
    fields.flagsFor = function (row) { return fields.flagSets[fields.flags[row]]; };
    fields.primarySlug = function (row) {
      var index = fields.primary[row];
      return index < 0 ? '' : fields.slugs[index];
    };
    return fields;
  }

  function decodeBundle(raw) {
    if (!raw || raw.version !== 1) throw new Error('unsupported accounts bundle version');
    var ids = requireArray(raw, 'ids');
    var count = ids.length;
    var columns = ['names', 'tier', 'score', 'groups', 'evidence', 'flags', 'primary', 'sources'];
    for (var i = 0; i < columns.length; i += 1) {
      if (requireArray(raw, columns[i]).length !== count) {
        throw new Error('accounts bundle column "' + columns[i] + '" has the wrong length');
      }
    }
    return makeDataset({
      count: count,
      ids: toIdArray(ids),
      names: raw.names,
      tiers: raw.tiers,
      tier: toInt32Array(raw.tier),
      scores: raw.scores,
      score: toInt32Array(raw.score),
      groups: toInt32Array(raw.groups),
      evidence: toInt32Array(raw.evidence),
      slugs: raw.slugs,
      sourceSets: raw.source_sets,
      sources: toInt32Array(raw.sources),
      flagSets: raw.flag_sets,
      flags: toInt32Array(raw.flags),
      primary: toInt32Array(raw.primary),
      legacyAvatars: null
    });
  }

  function splitList(value) {
    var seen = Object.create(null);
    var out = [];
    var parts = String(value === null || value === undefined ? '' : value).split(';');
    for (var i = 0; i < parts.length; i += 1) {
      var part = parts[i].trim();
      if (part && !seen[part]) { seen[part] = true; out.push(part); }
    }
    return out;
  }

  // Fallback path: build the same dataset straight from the public
  // accounts.json, used when the compact bundle is missing or does not
  // describe the same snapshot as meta.json.
  function datasetFromAccounts(rows) {
    var tiers = [], tierIndex = Object.create(null);
    var scores = [], scoreIndex = Object.create(null);
    var slugs = [], slugIndex = Object.create(null);
    var sourceSets = [], flagSets = [];
    var ids = [], names = [], tier = [], score = [], groups = [], evidence = [];
    var flags = [], primary = [], sources = [], legacyAvatars = [];

    function intern(list, index, value) {
      var at = index[value];
      if (at === undefined) { at = index[value] = list.length; list.push(value); }
      return at;
    }

    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i];
      var suffix = suffixOf(String(row.steamid64 || ''));
      if (suffix < 0) continue;
      var all = splitList(row.all_sources);
      var strongest = splitList(row.strongest_sources).filter(function (slug) {
        return all.indexOf(slug) !== -1;
      });
      var ordered = strongest.concat(all.filter(function (slug) {
        return strongest.indexOf(slug) === -1;
      }));

      ids.push(suffix);
      names.push(row.latest_name || '');
      tier.push(intern(tiers, tierIndex, row.confidence_tier || 'unscored'));
      score.push(intern(scores, scoreIndex, String(row.confidence_score || '')));
      groups.push(Number(row.independent_source_groups) || 0);
      evidence.push(Number(row.evidence_count) || 0);
      flagSets.push(splitList(row.flags));
      flags.push(flagSets.length - 1);
      primary.push(row.primary_source ? intern(slugs, slugIndex, row.primary_source) : -1);
      sourceSets.push(ordered.map(function (slug) { return intern(slugs, slugIndex, slug); }));
      sources.push(sourceSets.length - 1);
      legacyAvatars.push(row.avatar_url || '');
    }

    return makeDataset({
      count: ids.length,
      ids: toFloat64Array(ids),
      names: names,
      tiers: tiers,
      tier: toInt32Array(tier),
      scores: scores,
      score: toInt32Array(score),
      groups: toInt32Array(groups),
      evidence: toInt32Array(evidence),
      slugs: slugs,
      sourceSets: sourceSets,
      sources: toInt32Array(sources),
      flagSets: flagSets,
      flags: toInt32Array(flags),
      primary: toInt32Array(primary),
      legacyAvatars: legacyAvatars
    });
  }

  /* ---- profiles ------------------------------------------------------- */

  var EMPTY_PROFILES = {
    count: 0, ids: new Float64Array(0), names: [], blob: '',
    fetched: new Int32Array(0), state: new Int32Array(0),
    base: 'https://avatars.steamstatic.com/', size: '_medium.jpg', hashLength: 40,
    generatedAt: ''
  };

  function decodeProfiles(raw) {
    if (!raw || raw.version !== 1 || !Array.isArray(raw.ids)) return EMPTY_PROFILES;
    var hashLength = Number(raw.hash_length) || 40;
    var blob = typeof raw.avatars === 'string' ? raw.avatars : '';
    if (blob.length !== raw.ids.length * hashLength) return EMPTY_PROFILES;
    return {
      count: raw.ids.length,
      ids: toFloat64Array(raw.ids),
      names: Array.isArray(raw.names) ? raw.names : [],
      blob: blob,
      fetched: toInt32Array(raw.fetched || []),
      state: toInt32Array(raw.state || []),
      base: typeof raw.avatar_base === 'string' ? raw.avatar_base : EMPTY_PROFILES.base,
      size: typeof raw.avatar_size === 'string' ? raw.avatar_size : EMPTY_PROFILES.size,
      hashLength: hashLength,
      generatedAt: typeof raw.generated_at === 'string' ? raw.generated_at : ''
    };
  }

  // Entries are stored sorted, so the page can look one up without building a
  // 36,000-entry Map it would only ever use fifty rows of at a time.
  function profileSlot(profiles, suffix) {
    var low = 0;
    var high = profiles.count - 1;
    while (low <= high) {
      var mid = (low + high) >> 1;
      var value = profiles.ids[mid];
      if (value === suffix) return mid;
      if (value < suffix) low = mid + 1; else high = mid - 1;
    }
    return -1;
  }

  function profileName(profiles, slot) {
    return slot < 0 ? '' : (profiles.names[slot] || '');
  }

  function profileAvatarUrl(profiles, slot) {
    if (slot < 0) return '';
    var hash = profiles.blob.substr(slot * profiles.hashLength, profiles.hashLength);
    if (!hash || hash === NO_AVATAR || !HASH_RE.test(hash)) return '';
    return profiles.base + hash + profiles.size;
  }

  /* ---- query parsing --------------------------------------------------- */

  // Accents are folded so that searching "cafe" finds "café". Both the index
  // and the query go through this, so the two always agree.
  var COMBINING_MARKS = /[\u0300-\u036f]/g;

  function normalizeText(value) {
    var text = String(value === null || value === undefined ? '' : value);
    try {
      // Lowercase after decomposing, not before: NFKD turns a few characters
      // into uppercase letters of its own accord (™ becomes TM, № becomes No),
      // and folding first would leave those unmatched.
      text = text.normalize('NFKD').replace(COMBINING_MARKS, '');
    } catch (error) {
      /* an engine without NFKD still gets case-insensitive search */
    }
    return text.toLowerCase();
  }

  var MAX_ACCOUNT_ID = 9999999999 - STEAM3_BASE;

  function fromAccountId(accountId) {
    if (!Number.isInteger(accountId) || accountId < 0 || accountId > MAX_ACCOUNT_ID) return -1;
    return STEAM3_BASE + accountId;
  }

  var STEAM2_RE = /^steam_([0-5]):([01]):(\d{1,10})$/;
  var STEAM3_RE = /^\[?u:1:(\d{1,10})\]?$/;
  var PROFILE_URL_RE = /^(?:https?:\/\/)?(?:www\.)?(?:steamcommunity\.com\/profiles|steamhistory\.net\/id|steamid\.io\/lookup|steamrep\.com\/(?:profiles|search))\/(7656119\d{10})\b/;
  var VANITY_URL_RE = /^(?:https?:\/\/)?(?:www\.)?steamcommunity\.com\/id\/([^/?#\s]+)/;

  /* Works out what the visitor typed. Returns the account key when the input
   * names one account, plus the text to search for otherwise.
   *
   *   exact  - the input can only mean this one account, so a miss is a miss
   *            rather than a reason to go looking for the text somewhere else
   *   terms  - normalized words, all of which a row has to contain */
  function parseSearch(input) {
    var raw = String(input === null || input === undefined ? '' : input).trim();
    var lower = raw.toLowerCase();

    var urlMatch = PROFILE_URL_RE.exec(lower);
    if (urlMatch) return { id: suffixOf(urlMatch[1]), exact: true, terms: [] };

    if (/^7656119\d{10}$/.test(lower)) return { id: suffixOf(lower), exact: true, terms: [] };

    var steam2 = STEAM2_RE.exec(lower);
    if (steam2) {
      return { id: fromAccountId(Number(steam2[3]) * 2 + Number(steam2[2])), exact: true, terms: [] };
    }

    var steam3 = STEAM3_RE.exec(lower);
    if (steam3) return { id: fromAccountId(Number(steam3[1])), exact: true, terms: [] };

    // A vanity URL needs a Steam API call to resolve, which the site cannot
    // make. Search for the name instead — it is usually the persona name too.
    var vanity = VANITY_URL_RE.exec(lower);
    if (vanity) {
      try { lower = decodeURIComponent(vanity[1]); } catch (error) { lower = vanity[1]; }
    }

    // A bare number is most likely a Steam32 account ID, but it could also be
    // part of a player's name, so a miss falls through to the text search.
    var bare = /^\d{1,10}$/.test(lower) ? fromAccountId(Number(lower)) : -1;

    var terms = normalizeText(lower).split(/\s+/).filter(function (term) { return term.length > 0; });
    return { id: bare, exact: false, terms: terms };
  }

  /* ---- search --------------------------------------------------------- */

  // One lowercase blob for the whole database rather than one string per
  // account: a single native indexOf over a few megabytes beats 36,000
  // separate String.prototype.includes calls, and it is one allocation
  // instead of 36,000 for the garbage collector to keep track of.
  function buildSearchIndex(dataset, profiles, sourceLabel) {
    var setText = new Array(dataset.sourceSets.length);
    for (var s = 0; s < dataset.sourceSets.length; s += 1) {
      var set = dataset.sourceSets[s];
      var labels = new Array(set.length);
      for (var j = 0; j < set.length; j += 1) {
        labels[j] = sourceLabel(dataset.slugs[set[j]]);
      }
      setText[s] = normalizeText(labels.join(' ')).split(ROW_SEPARATOR).join(' ');
    }

    var flagText = new Array(dataset.flagSets.length);
    for (var f = 0; f < dataset.flagSets.length; f += 1) {
      flagText[f] = normalizeText(dataset.flagSets[f].join(' '));
    }

    var parts = new Array(dataset.count);
    var starts = new Int32Array(dataset.count + 1);
    var offset = 0;
    for (var i = 0; i < dataset.count; i += 1) {
      var suffix = dataset.ids[i];
      var persona = profiles ? profileName(profiles, profileSlot(profiles, suffix)) : '';
      var text = normalizeText(steamId64(suffix) + FIELD_SEPARATOR + steam3(suffix)
        + FIELD_SEPARATOR + dataset.names[i] + FIELD_SEPARATOR + persona)
        .split(ROW_SEPARATOR).join(' ')
        + FIELD_SEPARATOR + flagText[dataset.flags[i]]
        + FIELD_SEPARATOR + setText[dataset.sources[i]];
      parts[i] = text;
      starts[i] = offset;
      offset += text.length + 1;
    }
    starts[dataset.count] = offset;
    return { blob: parts.join(ROW_SEPARATOR), starts: starts };
  }

  function rowAtOffset(starts, offset) {
    var low = 0;
    var high = starts.length - 2;
    while (low < high) {
      var mid = (low + high + 1) >> 1;
      if (starts[mid] <= offset) low = mid; else high = mid - 1;
    }
    return low;
  }

  function allRows(count) {
    var out = new Int32Array(count);
    for (var i = 0; i < count; i += 1) out[i] = i;
    return out;
  }

  function rowsWithTier(dataset, tierIndex) {
    var out = new Int32Array(dataset.count);
    var n = 0;
    for (var i = 0; i < dataset.count; i += 1) {
      if (dataset.tier[i] === tierIndex) out[n++] = i;
    }
    return out.subarray(0, n);
  }

  function rowWithId(dataset, suffix) {
    for (var i = 0; i < dataset.count; i += 1) {
      if (dataset.ids[i] === suffix) return i;
    }
    return -1;
  }

  function rowText(index, row) {
    return index.blob.slice(index.starts[row], index.starts[row + 1] - 1);
  }

  // Driven by the longest term, because that is the one with fewest matches to
  // walk; the rest are checked against the matching rows only.
  function longestTerm(terms) {
    var best = 0;
    for (var i = 1; i < terms.length; i += 1) {
      if (terms[i].length > terms[best].length) best = i;
    }
    return best;
  }

  /* Returns row indices in database order. `index` may be null, in which case
   * a text query matches nothing until the index has been built; identifier
   * queries never need it. */
  function search(dataset, index, input, tier) {
    var tierIndex = tier ? dataset.tiers.indexOf(tier) : -1;
    if (tier && tierIndex < 0) return new Int32Array(0);

    var query = parseSearch(input);
    var matchesTier = function (row) { return tierIndex < 0 || dataset.tier[row] === tierIndex; };

    if (query.id >= 0) {
      var found = rowWithId(dataset, query.id);
      if (found >= 0) return matchesTier(found) ? Int32Array.of(found) : new Int32Array(0);
      if (query.exact) return new Int32Array(0);
    } else if (query.exact) {
      return new Int32Array(0);
    }

    if (!query.terms.length) {
      if (tierIndex < 0) return allRows(dataset.count);
      return rowsWithTier(dataset, tierIndex);
    }
    if (!index) return new Int32Array(0);

    var driver = longestTerm(query.terms);
    var needle = query.terms[driver];
    var matches = new Int32Array(dataset.count);
    var count = 0;
    var at = index.blob.indexOf(needle, 0);
    while (at !== -1) {
      var row = rowAtOffset(index.starts, at);
      if (matchesTier(row)) {
        var ok = true;
        if (query.terms.length > 1) {
          var text = rowText(index, row);
          for (var t = 0; t < query.terms.length && ok; t += 1) {
            if (t !== driver && text.indexOf(query.terms[t]) === -1) ok = false;
          }
        }
        if (ok) matches[count++] = row;
      }
      at = index.blob.indexOf(needle, index.starts[row + 1]);
    }
    return matches.subarray(0, count);
  }

  /* Strongest corroboration first. Ties fall back to database order so the
   * same query always produces the same page, and so paging is stable. */
  function sortByConfidence(dataset, rows) {
    var sorted = rows.slice();
    sorted.sort(function (a, b) {
      return dataset.scoreOf(b) - dataset.scoreOf(a) || a - b;
    });
    return sorted;
  }

  /* ---- source presentation ------------------------------------------- */

  var LEAGUE_SLUG_RE = /(rgl|etf2l|ugc|ozfortress|brasil-fortress)/;
  var MVM_SLUG_RE = /(mvmlobby|metalstats|tacobot)/;
  var BOT_SLUG_RE = /(bot-list|bots-tf|sleepy-bots)/;
  var TF2BD_SLUG_RE = /(pazer|tf2-bot-detector|tf2bd-trusted|minein4|garou3299|horizon)/;

  function sourceBadge(source) {
    if (!source) return 'Source';
    var slug = String(source.slug || '').toLowerCase();
    var type = String(source.source_type || '').toLowerCase();
    var method = String(source.assessment_method || '').toLowerCase();

    if (slug === 'valve-vac-ban') return 'VAC';
    if (slug === 'valve-tf2-game-ban') return 'Game ban';
    if (type === 'sourcebans' || type === 'community_bans') return 'Server ban';
    if (type === 'league_bans' || LEAGUE_SLUG_RE.test(slug)) return 'League ban';
    if (type === 'reviewed_report_database' || method.indexOf('reviewer-confirmed') !== -1) return 'Reviewed';
    if (type === 'mvm_reputation' || MVM_SLUG_RE.test(slug)) return 'MvM';
    if (BOT_SLUG_RE.test(slug)) return 'Bot list';
    if (TF2BD_SLUG_RE.test(slug) || type === 'tf2bd_playerlist') return 'TF2BD';
    if (type === 'compiled_playerlist' || type === 'public_playerlist'
      || type === 'community_list' || type === 'curated_database') return 'Player list';
    if (type === 'profile_history_enrichment') return 'History';
    if (type === 'aggregator' || type === 'mirror_index') return 'Reference';
    if (type === 'project_reference') return 'Project';
    return 'Source';
  }

  function tierLabel(value) {
    var text = String(value || 'unscored').split('_').join(' ');
    return text.charAt(0).toUpperCase() + text.slice(1);
  }

  // Everything the source column needs, worked out once per source instead of
  // once per rendered row.
  function prepareSources(rows) {
    var bySlug = new Map();
    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i];
      var slug = String(row.slug || '');
      if (!slug) continue;
      bySlug.set(slug, {
        slug: slug,
        name: row.name || slug,
        shortName: row.short_name || row.name || slug,
        badge: sourceBadge(row),
        url: safeUrl(row.upstream_repo || row.update_url || ''),
        scoring: String(row.counts_toward_confidence) === 'true'
      });
    }
    return bySlug;
  }

  return {
    ID_PREFIX: ID_PREFIX,
    NO_AVATAR: NO_AVATAR,
    escapeHtml: escapeHtml,
    safeUrl: safeUrl,
    steamId64: steamId64,
    steam3: steam3,
    suffixOf: suffixOf,
    normalizeText: normalizeText,
    parseSearch: parseSearch,
    decodeBundle: decodeBundle,
    datasetFromAccounts: datasetFromAccounts,
    decodeProfiles: decodeProfiles,
    emptyProfiles: EMPTY_PROFILES,
    profileSlot: profileSlot,
    profileName: profileName,
    profileAvatarUrl: profileAvatarUrl,
    buildSearchIndex: buildSearchIndex,
    rowAtOffset: rowAtOffset,
    search: search,
    sortByConfidence: sortByConfidence,
    sourceBadge: sourceBadge,
    tierLabel: tierLabel,
    prepareSources: prepareSources,
    splitList: splitList
  };
}());

if (typeof module === 'object' && module.exports) module.exports = SentinelData;
