'use strict';

(function (data) {
  var esc = data.escapeHtml;
  var rowsData = [];
  var timer = 0;

  var q = document.getElementById('q');
  var rows = document.getElementById('rows');
  var stats = document.getElementById('stats');
  var lastUpdate = document.getElementById('last-update');

  function typeLabel(value) {
    return String(value || '').split('_').join(' ').replace(/\b\w/g, function (c) {
      return c.toUpperCase();
    });
  }

  function render() {
    var terms = data.normalizeText(q.value).split(/\s+/).filter(Boolean);
    var visible = terms.length
      ? rowsData.filter(function (row) {
        return terms.every(function (term) { return row.search.indexOf(term) !== -1; });
      })
      : rowsData;

    stats.textContent = visible.length.toLocaleString() + ' of '
      + rowsData.length.toLocaleString() + ' registered sources';

    rows.innerHTML = visible.map(function (row) {
      var source = row.raw;
      var name = row.url
        ? '<a href="' + esc(row.url) + '" target="_blank" rel="noreferrer">' + esc(source.name) + '</a>'
        : esc(source.name);
      return '<tr><td class="mono">' + esc(source.source_id) + '</td>'
        + '<td>' + name + '</td>'
        + '<td>' + esc(typeLabel(source.source_type)) + '</td>'
        + '<td>' + esc(source.scope_region) + '</td>'
        + '<td class="mono">' + (Number(source.seed_record_count) || 0).toLocaleString() + '</td>'
        + '<td>' + esc(source.base_weight) + '</td>'
        + '<td>' + (String(source.counts_toward_confidence) === 'true' ? 'yes' : 'no') + '</td>'
        + '<td>' + esc(source.assessment_method) + '</td></tr>';
    }).join('');
  }

  q.addEventListener('input', function () {
    window.clearTimeout(timer);
    timer = window.setTimeout(render, 120);
  });

  fetch('data/sources.json').then(function (response) {
    return response.json();
  }).then(function (sourceRows) {
    rowsData = sourceRows.map(function (source) {
      return {
        raw: source,
        url: data.safeUrl(source.upstream_repo || source.update_url || ''),
        search: data.normalizeText([source.name, source.slug, source.source_type,
          source.scope_region, source.assessment_method, source.independence_group].join(' '))
      };
    });
    render();
  }).catch(function (error) {
    stats.textContent = 'Failed to load sources: ' + error.message;
  });

  fetch('data/meta.json').then(function (response) {
    return response.json();
  }).then(function (meta) {
    if (meta.last_database_update_display) {
      lastUpdate.textContent = 'Last database update: ' + meta.last_database_update_display;
    }
  }).catch(function () { /* the header keeps its placeholder */ });
}(SentinelData));
