'use strict';
let data = [];
let timer = null;
const q = document.getElementById('q');
const rows = document.getElementById('rows');
const stats = document.getElementById('stats');
const lastUpdate = document.getElementById('last-update');

function esc(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]); }
function sourceUrl(row) { return row.upstream_repo || row.update_url || ''; }
function typeLabel(value) { return String(value || '').replaceAll('_',' ').replace(/\b\w/g, c => c.toUpperCase()); }
function render() {
  const needle=q.value.trim().toLowerCase();
  const filtered=data.filter(row => !needle || row._search.includes(needle));
  stats.textContent=`${filtered.length.toLocaleString()} of ${data.length.toLocaleString()} registered sources`;
  rows.innerHTML=filtered.map(row=>{
    const url=sourceUrl(row);
    const name=url?`<a href="${esc(url)}" target="_blank" rel="noreferrer">${esc(row.name)}</a>`:esc(row.name);
    return `<tr><td class="mono">${esc(row.source_id)}</td><td>${name}</td><td>${esc(typeLabel(row.source_type))}</td><td>${esc(row.scope_region)}</td><td class="mono">${Number(row.seed_record_count||0).toLocaleString()}</td><td>${esc(row.base_weight)}</td><td>${row.counts_toward_confidence==='true'?'yes':'no'}</td><td>${esc(row.assessment_method)}</td></tr>`;
  }).join('');
}
q.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(render,120);});
fetch('data/sources.json').then(r=>r.json()).then(sourceData=>{data=sourceData.map(row=>({...row,_search:[row.name,row.slug,row.source_type,row.scope_region,row.assessment_method,row.independence_group].join(' ').toLowerCase()}));render();});
fetch('data/meta.json',{cache:'no-store'}).then(r=>r.json()).then(meta=>{if(meta.last_database_update_display)lastUpdate.textContent=`Last database update: ${meta.last_database_update_display}`;}).catch(()=>{});
