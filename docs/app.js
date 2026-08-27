/* Account table for TF2 Sentinel.
 *
 * The page loads three files: the compact accounts bundle, the source catalog
 * and the Steam profile cache. All three are generated in the repository, so a
 * visitor never talks to Steam and the number of requests does not depend on
 * how large the database gets. docs/lib/sentinel-data.js does the decoding and
 * searching; this file only renders.
 */
'use strict';

(function (data) {
  var PAGE_SIZE = 50;
  var SEARCH_DELAY_MS = 140;
  var PLACEHOLDER = 'avatar-placeholder.svg';
  // Rows near the top are fetched immediately; the rest wait until they are
  // scrolled towards, so one page view asks the CDN for a handful of images
  // rather than fifty.
  var EAGER_AVATARS = 8;
  // Left behind by the version of this page that fetched profiles from Steam
  // in the browser. Dropped so it stops occupying the visitor's storage quota.
  var RETIRED_STORAGE_KEYS = ['sentinel_avatar_cache_v1'];

  var FLAG_LABELS = {
    server_ban: 'Server ban (not cheating)',
    clear: 'Listed as legitimate',
    cheater_supporter: 'Cheater supporter'
  };

  var dataset = null;
  var profiles = data.emptyProfiles;
  var sources = new Map();
  var searchIndex = null;
  var filtered = new Int32Array(0);
  var page = 1;
  var expandedId = '';
  var searchTimer = 0;
  var idleHandle = 0;
  var warmedFrom = -1;

  var q = document.getElementById('q');
  var tier = document.getElementById('tier');
  var rows = document.getElementById('rows');
  var stats = document.getElementById('stats');
  var lastUpdate = document.getElementById('last-update');
  var profileUpdate = document.getElementById('profile-update');
  var pagerTop = document.getElementById('pager-top');
  var pagerBottom = document.getElementById('pager-bottom');

  var esc = data.escapeHtml;

  var whenIdle = window.requestIdleCallback
    ? function (fn) { return window.requestIdleCallback(fn, { timeout: 1500 }); }
    : function (fn) { return window.setTimeout(fn, 200); };
  var cancelIdle = window.cancelIdleCallback
    ? function (handle) { window.cancelIdleCallback(handle); }
    : function (handle) { window.clearTimeout(handle); };

  function sourceFor(slug) {
    return sources.get(slug) || null;
  }

  function sourceLabel(slug) {
    var source = sourceFor(slug);
    return source ? source.name : slug;
  }

  /* ---- rendering ------------------------------------------------------ */

  function sourceAnchor(source, slug, full) {
    var label = source ? (full ? source.name : source.shortName) : slug;
    var title = source ? source.name : slug;
    if (source && source.url) {
      return '<a class="source-link" href="' + esc(source.url) + '" target="_blank" rel="noreferrer"'
        + ' title="' + esc(title) + '">' + esc(label) + '</a>';
    }
    return '<span class="source-name" title="' + esc(title) + '">' + esc(label) + '</span>';
  }

  function priorityIndicators(slugs, primarySlug) {
    var html = '';
    if (primarySlug !== 'valve-tf2-game-ban' && slugs.indexOf('valve-tf2-game-ban') !== -1) {
      html += '<span class="signal-badge">Game ban</span>';
    }
    if (primarySlug !== 'valve-vac-ban' && slugs.indexOf('valve-vac-ban') !== -1) {
      html += '<span class="signal-badge">VAC</span>';
    }
    return html;
  }

  function sourceCell(row, steamid64) {
    var slugs = dataset.slugsFor(row);
    if (!slugs.length) return '<span class="muted">No source</span>';

    var primarySlug = dataset.primarySlug(row) || slugs[0];
    var primary = sourceFor(primarySlug);
    var badge = '<span class="source-badge">' + esc(primary ? primary.badge : 'Source') + '</span>';
    var more = slugs.length > 1
      ? '<button class="more-sources" type="button" data-expand="' + steamid64 + '"'
        + ' aria-expanded="' + (expandedId === steamid64) + '"'
        + ' title="Show all sources">+' + (slugs.length - 1) + '</button>'
      : '';
    return '<div class="source-summary">' + priorityIndicators(slugs, primarySlug) + badge
      + sourceAnchor(primary, primarySlug) + more + '</div>';
  }

  function sourceDetails(row) {
    var slugs = dataset.slugsFor(row);
    if (!slugs.length) return '';

    var items = '';
    for (var i = 0; i < slugs.length; i += 1) {
      var source = sourceFor(slugs[i]);
      var note = source && source.scoring
        ? ''
        : '<span class="muted no-weight">no confidence weight</span>';
      items += '<li><span class="source-badge">' + esc(source ? source.badge : 'Source') + '</span>'
        + sourceAnchor(source, slugs[i], true) + note + '</li>';
    }

    var flags = dataset.flagsFor(row);
    var chips = '';
    for (var f = 0; f < flags.length; f += 1) {
      chips += '<span class="flag-chip">' + esc(FLAG_LABELS[flags[f]] || flags[f]) + '</span>';
    }

    return '<tr class="detail-row"><td colspan="5"><div class="detail-panel">'
      + '<div><strong>Sources</strong><ul class="source-list">' + items + '</ul></div>'
      + '<div class="detail-meta">'
      + '<div><strong>Independent groups</strong><span>' + dataset.groups[row] + '</span></div>'
      + '<div><strong>Evidence rows</strong><span>' + dataset.evidence[row] + '</span></div>'
      + '<div><strong>Flags</strong><span class="flag-list">' + (chips || '—') + '</span></div>'
      + '</div></div></td></tr>';
  }

  function hasCheatingSignal(row) {
    var flags = dataset.flagsFor(row);
    for (var i = 0; i < flags.length; i += 1) {
      if (flags[i] !== 'server_ban' && flags[i] !== 'clear') return true;
    }
    return false;
  }

  function confidenceCell(row) {
    if (!hasCheatingSignal(row)) {
      return '<span class="confidence confidence-none" title="This account is listed only by'
        + ' records that do not assert cheating"><strong>—</strong><span>No cheating signal</span></span>';
    }
    var tierName = dataset.tiers[dataset.tier[row]];
    return '<span class="confidence confidence-' + esc(tierName) + '"><strong>'
      + esc(dataset.scores[dataset.score[row]]) + '</strong><span>'
      + esc(data.tierLabel(tierName)) + '</span></span>';
  }

  // Profiles are authoritative. accounts.json's avatar_url is only consulted on
  // the fallback path, and only if it is a Steam avatar URL we recognise.
  function avatarFor(row, slot) {
    var url = data.profileAvatarUrl(profiles, slot);
    if (url) return url;
    if (dataset.legacyAvatars) {
      var legacy = dataset.legacyAvatars[row];
      if (/^https:\/\/[a-z0-9.-]*steamstatic\.com\/[0-9a-f]{40}_(medium|full)\.jpg$/.test(legacy)) {
        return legacy;
      }
    }
    return PLACEHOLDER;
  }

  function accountRow(row, position) {
    var steamid64 = dataset.steamId64(row);
    var slot = data.profileSlot(profiles, dataset.ids[row]);
    var name = data.profileName(profiles, slot) || dataset.names[row] || 'Unknown';
    var expanded = expandedId === steamid64;
    var loading = position < EAGER_AVATARS
      ? ' loading="eager" fetchpriority="high"'
      : ' loading="lazy" fetchpriority="low"';

    var html = '<tr class="account-row' + (expanded ? ' expanded' : '') + '">'
      + '<td><div class="player-cell">'
      + '<img class="avatar" src="' + esc(avatarFor(row, slot)) + '" alt="" width="40" height="40"'
      + loading + ' decoding="async" referrerpolicy="no-referrer">'
      + '<span class="player-name" title="' + esc(name) + '">' + esc(name) + '</span>'
      + '</div></td>'
      + '<td><span class="steamid mono">' + steamid64 + '</span></td>'
      + '<td>' + confidenceCell(row) + '</td>'
      + '<td><div class="profile-links">'
      + '<a href="https://steamcommunity.com/profiles/' + steamid64 + '/" target="_blank" rel="noreferrer">Profile</a>'
      + '<a href="https://steamhistory.net/id/' + steamid64 + '" target="_blank" rel="noreferrer">History</a>'
      + '</div></td>'
      + '<td>' + sourceCell(row, steamid64) + '</td>'
      + '</tr>';
    return expanded ? html + sourceDetails(row) : html;
  }

  function pageCount() {
    return Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  }

  function pagerHtml() {
    var pages = pageCount();
    if (pages <= 1) return '';
    return '<button type="button" data-page="prev"' + (page <= 1 ? ' disabled' : '') + '>Previous</button>'
      + '<span>Page ' + page.toLocaleString() + ' of ' + pages.toLocaleString() + '</span>'
      + '<button type="button" data-page="next"' + (page >= pages ? ' disabled' : '') + '>Next</button>';
  }

  function renderPage(focusExpandFor) {
    if (!dataset) return;
    var pages = pageCount();
    if (page > pages) page = pages;

    var start = (page - 1) * PAGE_SIZE;
    var end = Math.min(start + PAGE_SIZE, filtered.length);
    var html = '';
    for (var i = start; i < end; i += 1) html += accountRow(filtered[i], i - start);

    stats.textContent = filtered.length
      ? (start + 1).toLocaleString() + '–' + end.toLocaleString() + ' of '
        + filtered.length.toLocaleString() + ' matching · ' + dataset.count.toLocaleString() + ' total'
      : 'No matching accounts · ' + dataset.count.toLocaleString() + ' total';

    rows.innerHTML = html;
    var pager = pagerHtml();
    pagerTop.innerHTML = pager;
    pagerBottom.innerHTML = pager;

    // The table is replaced wholesale, so a button that was activated has to be
    // focused again or keyboard users are dropped back to the top of the page.
    if (focusExpandFor && /^\d{17}$/.test(focusExpandFor)) {
      var button = rows.querySelector('[data-expand="' + focusExpandFor + '"]');
      if (button) button.focus();
    }

    scheduleWarmup(end);
  }

  /* ---- avatar loading ------------------------------------------------- */

  // One listener for the whole table instead of one per image. Image errors do
  // not bubble, so this listens during the capture phase.
  rows.addEventListener('error', function (event) {
    var img = event.target;
    if (!img || img.tagName !== 'IMG' || img.dataset.fallback) return;
    img.dataset.fallback = '1';
    img.src = PLACEHOLDER;
  }, true);

  // Put the next page's avatars in the browser cache while nothing else is
  // happening, so paging forward does not start from a blank column. Bounded to
  // one page; the browser's own cache stops a repeat visit from re-requesting.
  function scheduleWarmup(from) {
    if (idleHandle) { cancelIdle(idleHandle); idleHandle = 0; }
    var connection = navigator.connection;
    if (connection && (connection.saveData || /(^|-)2g$/.test(connection.effectiveType || ''))) return;

    var limit = Math.min(from + PAGE_SIZE, filtered.length);
    if (from >= limit || from === warmedFrom) return;
    warmedFrom = from;

    idleHandle = whenIdle(function () {
      idleHandle = 0;
      for (var i = from; i < limit; i += 1) {
        var row = filtered[i];
        var url = data.profileAvatarUrl(profiles, data.profileSlot(profiles, dataset.ids[row]));
        if (url) new Image().src = url;
      }
    });
  }

  /* ---- filtering ------------------------------------------------------ */

  function ensureSearchIndex() {
    if (!searchIndex && dataset) {
      searchIndex = data.buildSearchIndex(dataset, profiles, sourceLabel);
    }
    return searchIndex;
  }

  function applyFilters() {
    if (!dataset) return;
    // A query that can only be one account is answered straight from the id
    // column; anything else needs the text index, so build it now if the idle
    // callback has not got round to it.
    if (data.parseSearch(q.value).terms.length) ensureSearchIndex();
    filtered = data.search(dataset, searchIndex, q.value, tier.value);
    page = 1;
    expandedId = '';
    warmedFrom = -1;
    renderPage();
  }

  function scheduleSearch() {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(applyFilters, SEARCH_DELAY_MS);
  }

  function handleClick(event) {
    var target = event.target;
    if (!target || typeof target.closest !== 'function') return;
    var expand = target.closest('[data-expand]');
    if (expand) {
      var steamid64 = expand.getAttribute('data-expand');
      expandedId = expandedId === steamid64 ? '' : steamid64;
      renderPage(steamid64);
      return;
    }
    var pageButton = target.closest('[data-page]');
    if (!pageButton || pageButton.disabled) return;
    if (pageButton.getAttribute('data-page') === 'prev') page = Math.max(1, page - 1);
    else page = Math.min(pageCount(), page + 1);
    expandedId = '';
    renderPage();
    document.querySelector('.table-wrap').scrollIntoView({ block: 'start' });
  }

  q.addEventListener('input', scheduleSearch);
  tier.addEventListener('change', applyFilters);
  document.addEventListener('click', handleClick);

  /* ---- loading -------------------------------------------------------- */

  function getJson(path) {
    return fetch(path).then(function (response) {
      if (!response.ok) throw new Error(path + ': ' + response.status);
      return response.json();
    });
  }

  function setDataset(next) {
    dataset = next;
    searchIndex = null;
    applyFilters();
  }

  function loadFromAccountsJson() {
    return getJson('data/accounts.json').then(function (accountRows) {
      setDataset(data.datasetFromAccounts(accountRows));
    }).catch(function (error) {
      if (!dataset) stats.textContent = 'Failed to load database: ' + error.message;
    });
  }

  function start() {
    for (var i = 0; i < RETIRED_STORAGE_KEYS.length; i += 1) {
      try { window.localStorage.removeItem(RETIRED_STORAGE_KEYS[i]); } catch (error) { /* storage disabled */ }
    }

    var bundlePromise = getJson('data/accounts.compact.json');
    var sourcesPromise = getJson('data/sources.json');
    var profilesPromise = getJson('data/profiles.json').catch(function () { return null; });
    var metaPromise = getJson('data/meta.json').catch(function () { return null; });

    // Profiles are not on the critical path: the table renders from the bundle
    // and picks up avatars and persona names as soon as they arrive.
    profilesPromise.then(function (raw) {
      if (!raw) return;
      profiles = data.decodeProfiles(raw);
      if (profiles.count) {
        // The index was built without persona names; drop it and rebuild when
        // the browser is next idle rather than on the visitor's first keystroke.
        searchIndex = null;
        warmedFrom = -1;
        if (dataset) {
          renderPage();
          whenIdle(ensureSearchIndex);
        }
      }
      if (profileUpdate && profiles.generatedAt) {
        var when = new Date(profiles.generatedAt);
        if (!isNaN(when.getTime())) {
          profileUpdate.textContent = 'Steam profiles refreshed: ' + when.toISOString().slice(0, 10);
        }
      }
    }).catch(function () { /* the table keeps rendering without profile data */ });

    Promise.all([bundlePromise, sourcesPromise]).then(function (loaded) {
      sources = data.prepareSources(loaded[1]);
      setDataset(data.decodeBundle(loaded[0]));
      whenIdle(ensureSearchIndex);
      return metaPromise;
    }).then(function (meta) {
      // The bundle is generated from accounts.json; if the two describe
      // different snapshots the deployment is half-updated, so fall back to the
      // file that is the interface of record rather than showing stale rows.
      if (meta && dataset && typeof meta.unique_accounts === 'number'
        && meta.unique_accounts !== dataset.count) {
        return loadFromAccountsJson();
      }
      return null;
    }).catch(function () {
      return sourcesPromise.then(function (sourceRows) {
        sources = data.prepareSources(sourceRows);
      }).catch(function () { /* source labels fall back to slugs */ })
        .then(function () { return loadFromAccountsJson(); });
    });

    metaPromise.then(function (meta) {
      if (meta && meta.last_database_update_display) {
        lastUpdate.textContent = 'Last database update: ' + meta.last_database_update_display;
      }
    }).catch(function () { /* the header keeps its placeholder */ });
  }

  start();
}(SentinelData));
