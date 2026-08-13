'use strict';

const PAGE_SIZE = 50;
const SEARCH_DELAY_MS = 140;

let accounts = [];
let sources = new Map();
let filtered = [];
let page = 1;
let searchTimer = null;
let expandedSteamId = '';
let bySteamId = new Map();

const q = document.getElementById('q');
const tier = document.getElementById('tier');
const rows = document.getElementById('rows');
const stats = document.getElementById('stats');
const lastUpdate = document.getElementById('last-update');
const pagerTop = document.getElementById('pager-top');
const pagerBottom = document.getElementById('pager-bottom');

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[char]);
}

function tierLabel(value) {
  const text = String(value || 'unscored').replaceAll('_', ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function playerName(row) {
  return row.steam_persona_name || row.latest_name || 'Unknown';
}

function sourceUrl(source) {
  return source?.upstream_repo || source?.update_url || '';
}

function sourceBadge(source) {
  if (!source) return 'Source';
  const slug = String(source.slug || '').toLowerCase();
  const type = String(source.source_type || '').toLowerCase();
  const method = String(source.assessment_method || '').toLowerCase();

  if (slug === 'valve-vac-ban') return 'VAC';
  if (slug === 'valve-tf2-game-ban') return 'Game ban';
  if (type === 'sourcebans') return 'Server ban';
  if (type === 'league_bans' || /(rgl|etf2l|ugc|ozfortress|brasil-fortress)/.test(slug)) return 'League ban';
  if (type === 'reviewed_report_database' || method.includes('reviewer-confirmed')) return 'Reviewed';
  if (type === 'mvm_reputation' || /(mvmlobby|metalstats|tacobot)/.test(slug)) return 'MvM';
  if (/(bot-list|bots-tf|sleepy-bots)/.test(slug)) return 'Bot list';
  if (/(pazer|tf2-bot-detector|tf2bd-trusted|minein4|garou3299|horizon)/.test(slug)) return 'TF2BD';
  if (type === 'tf2bd_playerlist') return 'TF2BD';
  if (type === 'compiled_playerlist' || type === 'public_playerlist' || type === 'community_list' || type === 'curated_database') return 'Player list';
  if (type === 'community_bans') return 'Community ban';
  if (type === 'profile_history_enrichment') return 'History';
  if (type === 'aggregator' || type === 'mirror_index') return 'Reference';
  if (type === 'project_reference') return 'Project';
  return 'Source';
}

function sourceName(source, slug) {
  return source?.name || slug || 'Unknown source';
}

function sourceAnchor(source, slug) {
  const name = sourceName(source, slug);
  const url = sourceUrl(source);
  return url
    ? `<a class="source-link" href="${esc(url)}" target="_blank" rel="noreferrer">${esc(name)}</a>`
    : `<span class="source-name">${esc(name)}</span>`;
}

function getAllSourceSlugs(row) {
  return [...new Set(String(row.all_sources || '').split(';').map(v => v.trim()).filter(Boolean))];
}

function priorityIndicators(slugs, primarySlug) {
  const items = [];
  if (slugs.includes('valve-tf2-game-ban') && primarySlug !== 'valve-tf2-game-ban') items.push('Game ban');
  if (slugs.includes('valve-vac-ban') && primarySlug !== 'valve-vac-ban') items.push('VAC');
  return items.map(label => `<span class="signal-badge">${esc(label)}</span>`).join('');
}

function sourceCell(row) {
  const slugs = getAllSourceSlugs(row);
  if (!slugs.length) return '<span class="muted">No source</span>';

  const primarySlug = row.primary_source || slugs[0];
  const primary = sources.get(primarySlug);
  const rest = Math.max(0, slugs.length - 1);
  const badge = `<span class="source-badge">${esc(sourceBadge(primary))}</span>`;
  const important = priorityIndicators(slugs, primarySlug);
  const more = rest
    ? `<button class="more-sources" type="button" data-expand="${esc(row.steamid64)}" aria-expanded="${expandedSteamId === row.steamid64}" title="Show all sources">+${rest}</button>`
    : '';
  return `<div class="source-summary">${important}${badge}${sourceAnchor(primary, primarySlug)}${more}</div>`;
}

function sourceDetails(row) {
  const slugs = getAllSourceSlugs(row);
  if (!slugs.length) return '';
  const primary = row.primary_source;
  const ordered = primary && slugs.includes(primary)
    ? [primary, ...slugs.filter(slug => slug !== primary)]
    : slugs;
  const items = ordered.map(slug => {
    const source = sources.get(slug);
    return `<li><span class="source-badge">${esc(sourceBadge(source))}</span>${sourceAnchor(source, slug)}</li>`;
  }).join('');
  const flags = String(row.flags || '').split(';').filter(Boolean).map(flag => `<span class="flag-chip">${esc(flag)}</span>`).join('');
  return `<tr class="detail-row">
    <td colspan="5">
      <div class="detail-panel">
        <div>
          <strong>Sources</strong>
          <ul class="source-list">${items}</ul>
        </div>
        <div class="detail-meta">
          <div><strong>Independent groups</strong><span>${esc(row.independent_source_groups)}</span></div>
          <div><strong>Evidence rows</strong><span>${esc(row.evidence_count)}</span></div>
          <div><strong>Flags</strong><span class="flag-list">${flags || '—'}</span></div>
        </div>
      </div>
    </td>
  </tr>`;
}

function avatarUrl(row) {
  if (row.avatar_url) return row.avatar_url;
  return 'avatar-placeholder.svg';
}

function accountRow(row) {
  const profileUrl = row.steam_profile_url || `https://steamcommunity.com/profiles/${row.steamid64}/`;
  const historyUrl = row.steamhistory_url || `https://steamhistory.net/id/${row.steamid64}`;
  const expanded = expandedSteamId === row.steamid64;
  const main = `<tr class="account-row${expanded ? ' expanded' : ''}">
    <td>
      <div class="player-cell">
        <img class="avatar" src="${esc(avatarUrl(row))}" alt="" width="40" height="40" loading="lazy" decoding="async" referrerpolicy="no-referrer" data-avatar>
        <span class="player-name" title="${esc(playerName(row))}">${esc(playerName(row))}</span>
      </div>
    </td>
    <td><span class="steamid mono">${esc(row.steamid64)}</span></td>
    <td><span class="confidence confidence-${esc(row.confidence_tier)}"><strong>${esc(row.confidence_score)}</strong><span>${esc(tierLabel(row.confidence_tier))}</span></span></td>
    <td><div class="profile-links"><a href="${esc(profileUrl)}" target="_blank" rel="noreferrer">Profile</a><a href="${esc(historyUrl)}" target="_blank" rel="noreferrer">History</a></div></td>
    <td>${sourceCell(row)}</td>
  </tr>`;
  return expanded ? main + sourceDetails(row) : main;
}

function pageCount() {
  return Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
}

function pagerHtml() {
  const pages = pageCount();
  if (pages <= 1) return '';
  const previousDisabled = page <= 1 ? ' disabled' : '';
  const nextDisabled = page >= pages ? ' disabled' : '';
  return `<button type="button" data-page="prev"${previousDisabled}>Previous</button><span>Page ${page.toLocaleString()} of ${pages.toLocaleString()}</span><button type="button" data-page="next"${nextDisabled}>Next</button>`;
}

function renderPage() {
  const pages = pageCount();
  if (page > pages) page = pages;
  const start = (page - 1) * PAGE_SIZE;
  const visible = filtered.slice(start, start + PAGE_SIZE);
  const from = filtered.length ? start + 1 : 0;
  const to = Math.min(start + PAGE_SIZE, filtered.length);

  stats.textContent = filtered.length
    ? `${from.toLocaleString()}–${to.toLocaleString()} of ${filtered.length.toLocaleString()} matching · ${accounts.length.toLocaleString()} total`
    : `No matching accounts · ${accounts.length.toLocaleString()} total`;

  rows.innerHTML = visible.map(accountRow).join('');
  const pager = pagerHtml();
  pagerTop.innerHTML = pager;
  pagerBottom.innerHTML = pager;

  rows.querySelectorAll('[data-avatar]').forEach(img => {
    img.addEventListener('error', () => {
      img.removeAttribute('data-avatar');
      img.src = 'avatar-placeholder.svg';
    }, { once: true });
  });
}

function applyFilters() {
  const needle = q.value.trim().toLowerCase();
  const selectedTier = tier.value;

  if (/^7656119\d{10}$/.test(needle) && bySteamId.has(needle)) {
    const row = bySteamId.get(needle);
    filtered = !selectedTier || row.confidence_tier === selectedTier ? [row] : [];
  } else {
    filtered = accounts.filter(row => {
      if (selectedTier && row.confidence_tier !== selectedTier) return false;
      return !needle || row._search.includes(needle);
    });
  }

  page = 1;
  expandedSteamId = '';
  renderPage();
}

function scheduleSearch() {
  window.clearTimeout(searchTimer);
  searchTimer = window.setTimeout(applyFilters, SEARCH_DELAY_MS);
}

function handleClick(event) {
  const expand = event.target.closest('[data-expand]');
  if (expand) {
    expandedSteamId = expandedSteamId === expand.dataset.expand ? '' : expand.dataset.expand;
    renderPage();
    return;
  }
  const pageButton = event.target.closest('[data-page]');
  if (!pageButton || pageButton.disabled) return;
  if (pageButton.dataset.page === 'prev') page = Math.max(1, page - 1);
  if (pageButton.dataset.page === 'next') page = Math.min(pageCount(), page + 1);
  expandedSteamId = '';
  renderPage();
  document.querySelector('.table-wrap').scrollIntoView({ block: 'start' });
}

function updateStickyOffset() {
  const tools = document.querySelector('.sticky-tools');
  if (!tools) return;
  document.documentElement.style.setProperty('--sticky-tools-height', `${Math.ceil(tools.getBoundingClientRect().height)}px`);
}

q.addEventListener('input', scheduleSearch);
tier.addEventListener('change', applyFilters);
document.addEventListener('click', handleClick);
window.addEventListener('resize', updateStickyOffset, { passive: true });
if ('ResizeObserver' in window) new ResizeObserver(updateStickyOffset).observe(document.querySelector('.sticky-tools'));
updateStickyOffset();

Promise.all([
  fetch('data/accounts.json').then(response => {
    if (!response.ok) throw new Error(`accounts.json: ${response.status}`);
    return response.json();
  }),
  fetch('data/sources.json').then(response => {
    if (!response.ok) throw new Error(`sources.json: ${response.status}`);
    return response.json();
  })
]).then(([accountData, sourceData]) => {
  sources = new Map(sourceData.map(source => [source.slug, source]));
  accounts = accountData.map(row => {
    const sourceNames = getAllSourceSlugs(row).map(slug => sourceName(sources.get(slug), slug));
    row._search = [
      row.steamid64, row.steam3, row.latest_name, row.steam_persona_name,
      row.flags, ...sourceNames
    ].filter(Boolean).join(' ').toLowerCase();
    return row;
  });
  bySteamId = new Map(accounts.map(row => [row.steamid64, row]));
  filtered = accounts;
  renderPage();
}).catch(error => {
  stats.textContent = `Failed to load database: ${error.message}`;
});

fetch('data/meta.json', { cache: 'no-store' })
  .then(response => response.json())
  .then(meta => {
    if (meta.last_database_update_display) {
      lastUpdate.textContent = `Last database update: ${meta.last_database_update_display}`;
    }
  })
  .catch(() => {});
