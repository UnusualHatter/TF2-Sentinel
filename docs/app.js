let accounts = [];
let sources = new Map();

const q = document.getElementById('q');
const tier = document.getElementById('tier');
const rows = document.getElementById('rows');
const stats = document.getElementById('stats');
const lastUpdate = document.getElementById('last-update');

function esc(value) {
  return String(value ?? '').replace(/[&<>"]/g, char => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;'
  })[char]);
}

function tierLabel(value) {
  return String(value || 'unscored').replace('_', ' ');
}

function sourceLink(slug) {
  const source = sources.get(slug);
  if (!source) return esc(slug);
  const url = source.upstream_repo || source.update_url || '';
  const name = source.name || slug;
  return url
    ? `<a target="_blank" rel="noreferrer" href="${esc(url)}">${esc(name)}</a>`
    : esc(name);
}

function playerName(row) {
  return row.steam_persona_name || row.latest_name || 'Unknown';
}

function sourceSummary(row) {
  const source = row.primary_source ? sourceLink(row.primary_source) : '—';
  const moreSources = Math.max(0, Number(row.source_count || 0) - 1);
  if (!moreSources) return source;
  const allNames = String(row.all_source_names || '').split(';').filter(Boolean).join(' · ');
  return `${source}<span class="muted source-more" title="${esc(allNames)}"> +${moreSources} more</span>`;
}

function render() {
  const needle = q.value.trim().toLowerCase();
  const selectedTier = tier.value;
  const filtered = accounts.filter(row => {
    if (selectedTier && row.confidence_tier !== selectedTier) return false;
    if (!needle) return true;
    return [
      row.steamid64,
      row.steam3,
      row.latest_name,
      row.steam_persona_name,
      row.flags,
      row.primary_source,
      row.primary_source_name,
      row.strongest_sources,
      row.strongest_source_names,
      row.all_sources,
      row.all_source_names
    ].join(' ').toLowerCase().includes(needle);
  });

  const visible = filtered.slice(0, 1000);
  stats.textContent = `Showing ${visible.length.toLocaleString()} of ${filtered.length.toLocaleString()} matching accounts · ${accounts.length.toLocaleString()} total`;

  rows.innerHTML = visible.map(row => {
    const avatar = row.avatar_url || 'avatar-placeholder.svg';
    const profileUrl = row.steam_profile_url || `https://steamcommunity.com/profiles/${row.steamid64}/`;
    const historyUrl = row.steamhistory_url || `https://steamhistory.net/id/${row.steamid64}`;
    return `<tr>
      <td>
        <div class="player-cell">
          <img class="avatar" src="${esc(avatar)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='avatar-placeholder.svg'">
          <span>${esc(playerName(row))}</span>
        </div>
      </td>
      <td class="mono"><a target="_blank" rel="noreferrer" href="${esc(profileUrl)}">${esc(row.steamid64)}</a></td>
      <td>
        <span class="confidence confidence-${esc(row.confidence_tier)}">${esc(row.confidence_score)} · ${esc(tierLabel(row.confidence_tier))}</span>
      </td>
      <td class="links">
        <a target="_blank" rel="noreferrer" href="${esc(profileUrl)}">Profile</a>
        <a target="_blank" rel="noreferrer" href="${esc(historyUrl)}">History</a>
      </td>
      <td>${sourceSummary(row)}</td>
      <td>${esc(row.raw_source_signals)}</td>
      <td>${esc(row.evidence_count)}</td>
    </tr>`;
  }).join('');
}

q.addEventListener('input', render);
tier.addEventListener('change', render);

Promise.all([
  fetch('data/accounts.json').then(response => response.json()),
  fetch('data/sources.json').then(response => response.json())
]).then(([accountData, sourceData]) => {
  accounts = accountData;
  sources = new Map(sourceData.map(source => [source.slug, source]));
  render();
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
