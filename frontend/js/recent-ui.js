import { apiFetch } from './api.js';

function isFilled(v) {
  return v !== undefined && v !== null && String(v).trim() !== '';
}

function pipelineComplete(p) {
  if (!p) return false;
  return ['address_line1', 'city', 'postcode', 'state_region', 'country_code'].every((k) => isFilled(p[k]));
}

function tdText(text, cls = '') {
  const td = document.createElement('td');
  td.textContent = text || '';
  if (cls) td.className = cls;
  return td;
}

function tdAlerts(warnings) {
  const td = document.createElement('td');
  td.className = 'cellAlerts';
  const notes = [];
  if (warnings && warnings.length) notes.push(...warnings);
  td.textContent = notes.join('; ');
  return td;
}

export async function loadRecent() {
  const data = await apiFetch('/recent?limit=10');
  const tbody = document.querySelector('#recent');
  tbody.innerHTML = '';
  for (const it of data.items || []) {
    const tr = document.createElement('tr');
    const tdWhen = document.createElement('td');
    tdWhen.textContent = it.created_at || '';
    const tdInp = document.createElement('td');
    tdInp.textContent = it.raw_address_preview || '';

    const p1 = it.pipelines?.bedrock_geonames;
    const p2 = it.pipelines?.libpostal_geonames;
    const p3 = it.pipelines?.aws_services;
    const p4 = it.pipelines?.loqate;

    const cls1 = pipelineComplete(p1) ? 'cellComplete' : 'cellIncomplete';
    const cls2 = pipelineComplete(p2) ? 'cellComplete' : 'cellIncomplete';
    const cls3 = pipelineComplete(p3) ? 'cellComplete' : 'cellIncomplete';
    const cls4 = pipelineComplete(p4) ? 'cellComplete' : 'cellIncomplete';

    tr.appendChild(tdWhen);
    tr.appendChild(tdInp);

    const rows = [
      [p1, cls1, it.model_id || ''],
      [p2, cls2, null],
      [p3, cls3, null],
      [p4, cls4, null],
    ];

    for (const [pipeline, cls, modelId] of rows) {
      const first = tdText(pipeline?.address_line1, cls);
      first.classList.add('groupStart');
      tr.appendChild(first);
      tr.appendChild(tdText(pipeline?.city, cls));
      tr.appendChild(tdText(pipeline?.postcode, cls));
      tr.appendChild(tdText(pipeline?.state_region, cls));
      tr.appendChild(tdText(pipeline?.country_code, cls));
      if (modelId !== null) tr.appendChild(tdText(modelId, cls));
      const alerts = tdAlerts(pipeline?.warnings);
      alerts.classList.add(cls);
      tr.appendChild(alerts);
    }

    tbody.appendChild(tr);
  }
}
