import { apiFetch } from './api.js';
import { setStatus } from './ui.js';

export async function loadCountries() {
  const resp = await fetch('./countries.min.json');
  if (!resp.ok) throw new Error('Failed to load countries list');
  const countries = await resp.json();

  const sel = document.querySelector('#country');
  sel.innerHTML = '<option value="">Auto-detect from address</option>';
  for (const c of countries) {
    const opt = document.createElement('option');
    opt.value = c.code;
    opt.textContent = `${c.name} (${c.code})`;
    sel.appendChild(opt);
  }
}

export async function loadModels() {
  const sel = document.querySelector('#modelId');
  sel.innerHTML = '<option value="">Loading…</option>';
  const data = await apiFetch('/models');
  sel.innerHTML = '<option value="">(select)</option>';

  const profs = data.inference_profiles || [];
  if (profs.length) {
    const og = document.createElement('optgroup');
    og.label = 'Inference profiles (recommended)';
    for (const p of profs) {
      const opt = document.createElement('option');
      opt.value = p.arn;
      opt.textContent = `${p.name}`;
      og.appendChild(opt);
    }
    sel.appendChild(og);
  }

  const models = data.models || [];
  if (models.length) {
    const og2 = document.createElement('optgroup');
    og2.label = 'Foundation models';
    for (const m of models) {
      const opt = document.createElement('option');
      opt.value = m.modelId;
      const supported = !!m.adapter_supported;
      opt.disabled = !supported;
      opt.textContent = supported
        ? `${m.provider} — ${m.name}`
        : `${m.provider} — ${m.name} (adapter not implemented)`;
      og2.appendChild(opt);
    }
    sel.appendChild(og2);
  }
}

export async function loadPrompt() {
  try {
    const data = await apiFetch('/prompt');
    const tpl = data.prompt_template || '';
    document.querySelector('#promptTemplate').value = tpl;
    sessionStorage.setItem('prompt_template_last', tpl);

    const pricing = data.pricing || {};
    document.querySelector('#priceIn').value = pricing.bedrock_input_usd_per_million ?? '';
    document.querySelector('#priceOut').value = pricing.bedrock_output_usd_per_million ?? '';
    document.querySelector('#priceLoc').value = pricing.location_usd_per_request ?? '';
  } catch {
    const last = sessionStorage.getItem('prompt_template_last') || '';
    document.querySelector('#promptTemplate').value = last;
  }
}

export async function savePrompt() {
  const tpl = document.querySelector('#promptTemplate').value;
  const pricing = {
    bedrock_input_usd_per_million: Number(document.querySelector('#priceIn').value || 0),
    bedrock_output_usd_per_million: Number(document.querySelector('#priceOut').value || 0),
    location_usd_per_request: Number(document.querySelector('#priceLoc').value || 0),
  };

  await apiFetch('/prompt', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_template: tpl, pricing }),
  });
  sessionStorage.setItem('prompt_template_last', tpl);
  setStatus('Prompt + pricing saved.');
}

export function renderPromptPreview() {
  const tpl = document.querySelector('#promptTemplate').value || '';
  const country = document.querySelector('#country').value || '';
  const address = document.querySelector('#address').value || '';
  const out = tpl.replaceAll('{country}', country).replaceAll('{address}', address);
  document.querySelector('#renderedPrompt').textContent = out;
}
