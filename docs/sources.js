let data = [];

const q = document.getElementById('q');
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

function sourceUrl(row) {
  return row.upstream_repo || row.update_url || '';
}

function render() {
  const needle = q.value.trim().toLowerCase();
  const filtered = data.filter(row => !needle || [
    row.name,
    row.slug,
    row.source_type,
    row.scope_region,
    row.assessment_method
  ].join(' ').toLowerCase().includes(needle));

  stats.textContent = `${filtered.length.toLocaleString()} of ${data.length.toLocaleString()} sources`;
  rows.innerHTML = filtered.map(row => {
    const url = sourceUrl(row);
    const name = url
      ? `<a target="_blank" rel="noreferrer" href="${esc(url)}">${esc(row.name)}</a>`
      : esc(row.name);
    return `<tr>
      <td>${esc(row.source_id)}</td>
      <td>${name}</td>
      <td>${esc(row.source_type)}</td>
      <td>${esc(row.scope_region)}</td>
      <td class="score">${esc(row.base_weight)}</td>
      <td>${row.counts_toward_confidence === 'true' ? 'yes' : 'no'}</td>
      <td>${esc(row.assessment_method)}</td>
    </tr>`;
  }).join('');
}

q.addEventListener('input', render);

fetch('data/sources.json')
  .then(response => response.json())
  .then(sourceData => {
    data = sourceData;
    render();
  });

fetch('data/meta.json', { cache: 'no-store' })
  .then(response => response.json())
  .then(meta => {
    if (meta.last_database_update_display) {
      lastUpdate.textContent = `Last database update: ${meta.last_database_update_display}`;
    }
  })
  .catch(() => {});
