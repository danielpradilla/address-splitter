/* global window, crypto */

function getConfig() {
  const cfg = window.__CONFIG__;
  if (!cfg || !cfg.apiBaseUrl || !cfg.cognitoDomain || !cfg.cognitoClientId || !cfg.redirectUri) {
    throw new Error('Missing window.__CONFIG__ (config.js not loaded)');
  }
  return cfg;
}

function b64url(bytes) {
  const bin = String.fromCharCode(...bytes);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}

async function sha256Base64Url(str) {
  const data = new TextEncoder().encode(str);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return b64url(new Uint8Array(digest));
}

function randomVerifier(len = 64) {
  const arr = new Uint8Array(len);
  crypto.getRandomValues(arr);
  return b64url(arr);
}

function qs(obj) {
  return Object.entries(obj)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
}

function setStatus(msg) {
  const el = document.querySelector('#status');
  if (el) el.textContent = msg;
}

function renderVersion() {
  try {
    const cfg = getConfig();
    const v = document.querySelector('#version');
    if (!v) return;
    const id = cfg.deployId ? String(cfg.deployId).slice(0, 12) : 'unknown';
    const t = cfg.deployTime || '';
    v.textContent = `deploy ${id}${t ? ' · ' + t : ''}`;
  } catch {
    // ignore
  }
}

function setError(msg) {
  const el = document.querySelector('#error');
  if (el) {
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
  }
}

function tokenStore() {
  return {
    get: () => {
      const raw = sessionStorage.getItem('tokens');
      return raw ? JSON.parse(raw) : null;
    },
    set: (t) => sessionStorage.setItem('tokens', JSON.stringify(t)),
    clear: () => sessionStorage.removeItem('tokens'),
  };
}

async function refreshTokens() {
  const cfg = getConfig();
  const tokens = tokenStore().get();
  if (!tokens?.refresh_token) throw new Error('No refresh token available');

  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    client_id: cfg.cognitoClientId,
    refresh_token: tokens.refresh_token,
  });

  const resp = await fetch(`${cfg.cognitoDomain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`Refresh failed: ${resp.status} ${t}`);
  }

  const fresh = await resp.json();
  // refresh response usually doesn't include refresh_token; keep the old one
  tokenStore().set({
    ...tokens,
    ...fresh,
    refresh_token: tokens.refresh_token,
  });
}

async function startLogin() {
  const cfg = getConfig();
  const verifier = randomVerifier();
  const challenge = await sha256Base64Url(verifier);
  const state = randomVerifier(16);

  sessionStorage.setItem('pkce_verifier', verifier);
  sessionStorage.setItem('oauth_state', state);

  const url = `${cfg.cognitoDomain}/oauth2/authorize?` + qs({
    response_type: 'code',
    client_id: cfg.cognitoClientId,
    redirect_uri: cfg.redirectUri,
    scope: 'openid email',
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  });
  window.location.assign(url);
}

async function exchangeCodeForTokens(code) {
  const cfg = getConfig();
  const verifier = sessionStorage.getItem('pkce_verifier');
  if (!verifier) throw new Error('Missing PKCE verifier');

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: cfg.cognitoClientId,
    code,
    redirect_uri: cfg.redirectUri,
    code_verifier: verifier,
  });

  const resp = await fetch(`${cfg.cognitoDomain}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`Token exchange failed: ${resp.status} ${t}`);
  }
  return await resp.json();
}

function logout() {
  const cfg = getConfig();
  tokenStore().clear();
  const url = `${cfg.cognitoDomain}/logout?` + qs({
    client_id: cfg.cognitoClientId,
    logout_uri: cfg.redirectUri,
  });
  window.location.assign(url);
}

async function apiFetch(path, opts = {}) {
  const cfg = getConfig();
  const tokens = tokenStore().get();
  if (!tokens?.id_token) throw new Error('Not authenticated');

  const doReq = async () => {
    const t = tokenStore().get();
    const headers = Object.assign({}, opts.headers || {}, {
      Authorization: `Bearer ${t.id_token}`,
    });
    return await fetch(cfg.apiBaseUrl + path, Object.assign({}, opts, { headers }));
  };

  let resp = await doReq();
  if (resp.status === 401) {
    // try refresh once
    await refreshTokens();
    resp = await doReq();
  }

  const text = await resp.text();
  let data;
  try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
  if (!resp.ok) {
    throw new Error(data?.message || data?.error || `API error ${resp.status}`);
  }
  return data;
}

function render() {
  const tokens = tokenStore().get();
  document.querySelector('#authState').textContent = tokens?.id_token ? 'Signed in' : 'Signed out';
  document.querySelector('#btnLogin').style.display = tokens?.id_token ? 'none' : 'inline-block';
  document.querySelector('#btnLogout').style.display = tokens?.id_token ? 'inline-block' : 'none';
  document.querySelector('#app').style.display = tokens?.id_token ? 'block' : 'none';
}

async function loadModels() {
  const sel = document.querySelector('#modelId');
  sel.innerHTML = '<option value="">Loading…</option>';
  const data = await apiFetch('/models');
  sel.innerHTML = '<option value="">(select)</option>';

  // Prefer inference profiles (work for models that require them)
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

async function loadCountries() {
  const resp = await fetch('./countries.min.json');
  if (!resp.ok) throw new Error('Failed to load countries list');
  const countries = await resp.json();

  const sel = document.querySelector('#country');
  // preserve first option (auto)
  sel.innerHTML = '<option value="">Auto-detect from address</option>';
  for (const c of countries) {
    const opt = document.createElement('option');
    opt.value = c.code;
    opt.textContent = `${c.name} (${c.code})`;
    sel.appendChild(opt);
  }
}

async function loadPrompt() {
  // Prefer server-persisted template; fallback to last local value if server errors.
  try {
    const data = await apiFetch('/prompt');
    const tpl = data.prompt_template || '';
    document.querySelector('#promptTemplate').value = tpl;
    sessionStorage.setItem('prompt_template_last', tpl);

    const pricing = data.pricing || {};
    document.querySelector('#priceIn').value = pricing.bedrock_input_usd_per_million ?? '';
    document.querySelector('#priceOut').value = pricing.bedrock_output_usd_per_million ?? '';
    document.querySelector('#priceLoc').value = pricing.location_usd_per_request ?? '';
  } catch (e) {
    const last = sessionStorage.getItem('prompt_template_last') || '';
    document.querySelector('#promptTemplate').value = last;
  }
}

async function savePrompt() {
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
  // also keep a local fallback
  sessionStorage.setItem('prompt_template_last', tpl);
  setStatus('Prompt + pricing saved.');
}

function renderPromptPreview() {
  const tpl = document.querySelector('#promptTemplate').value || '';
  const country = document.querySelector('#country').value || '';
  const address = document.querySelector('#address').value || '';
  const out = tpl.replaceAll('{country}', country).replaceAll('{address}', address);
  document.querySelector('#renderedPrompt').textContent = out;
}

async function doSplit() {
  setError('');
  setStatus('Splitting…');

  const payload = {
    country_code: (document.querySelector('#country').value || '').trim(),
    raw_address: (document.querySelector('#address').value || '').trim(),
    modelId: (document.querySelector('#modelId').value || '').trim(),
    pipelines: [
      document.querySelector('#p1').checked ? 'bedrock_geonames' : null,
      document.querySelector('#p2').checked ? 'libpostal_geonames' : null,
      document.querySelector('#p3').checked ? 'aws_services' : null,
    ].filter(Boolean),
  };

  if (!payload.raw_address) {
    throw new Error('Please fill in Address.');
  }
  if (payload.pipelines.includes('bedrock_geonames') && !payload.modelId) {
    throw new Error('Select a Bedrock model or inference profile for pipeline #1.');
  }

  const data = await apiFetch('/split', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  document.querySelector('#results').textContent = JSON.stringify(data, null, 2);
  setStatus('Done.');
  await loadRecent();
}

function isFilled(v) {
  return v !== undefined && v !== null && String(v).trim() !== '';
}

function pipelineComplete(p) {
  if (!p) return false;
  // minimal “all fields filled” check for quick visual scan
  return ['address_line1', 'city', 'postcode', 'state_region', 'country_code'].every(k => isFilled(p[k]));
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
  td.textContent = (warnings && warnings.length) ? warnings.join('; ') : '';
  return td;
}

async function loadRecent() {
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

    const cls1 = pipelineComplete(p1) ? 'cellComplete' : 'cellIncomplete';
    const cls2 = pipelineComplete(p2) ? 'cellComplete' : 'cellIncomplete';
    const cls3 = pipelineComplete(p3) ? 'cellComplete' : 'cellIncomplete';

    tr.appendChild(tdWhen);
    tr.appendChild(tdInp);

    // Pipeline 1 fields
    tr.appendChild(tdText(p1?.address_line1, cls1));
    tr.appendChild(tdText(p1?.city, cls1));
    tr.appendChild(tdText(p1?.postcode, cls1));
    tr.appendChild(tdText(p1?.state_region, cls1));
    tr.appendChild(tdText(p1?.country_code, cls1));
    const a1 = tdAlerts(p1?.warnings);
    a1.classList.add(cls1);
    tr.appendChild(a1);

    // Pipeline 2 fields
    tr.appendChild(tdText(p2?.address_line1, cls2));
    tr.appendChild(tdText(p2?.city, cls2));
    tr.appendChild(tdText(p2?.postcode, cls2));
    tr.appendChild(tdText(p2?.state_region, cls2));
    tr.appendChild(tdText(p2?.country_code, cls2));
    const a2 = tdAlerts(p2?.warnings);
    a2.classList.add(cls2);
    tr.appendChild(a2);

    // Pipeline 3 fields
    tr.appendChild(tdText(p3?.address_line1, cls3));
    tr.appendChild(tdText(p3?.city, cls3));
    tr.appendChild(tdText(p3?.postcode, cls3));
    tr.appendChild(tdText(p3?.state_region, cls3));
    tr.appendChild(tdText(p3?.country_code, cls3));
    const a3 = tdAlerts(p3?.warnings);
    a3.classList.add(cls3);
    tr.appendChild(a3);

    tbody.appendChild(tr);
  }
}

async function init() {
  try {
    // Handle OAuth callback
    const url = new URL(window.location.href);
    const code = url.searchParams.get('code');
    const state = url.searchParams.get('state');

    if (code) {
      const expected = sessionStorage.getItem('oauth_state');
      if (!expected || expected !== state) {
        throw new Error('OAuth state mismatch');
      }
      setStatus('Completing sign-in…');
      const tokens = await exchangeCodeForTokens(code);
      tokenStore().set(tokens);
      // clean URL
      url.searchParams.delete('code');
      url.searchParams.delete('state');
      window.history.replaceState({}, document.title, url.toString());
    }

    render();

    document.querySelector('#btnLogin').addEventListener('click', () => startLogin().catch(e => setError(e.message)));
    document.querySelector('#btnLogout').addEventListener('click', () => logout());

    if (tokenStore().get()?.id_token) {
      await loadCountries();
      await loadModels();
      await loadPrompt();
      await loadRecent();
    }

    document.querySelector('#btnSavePrompt').addEventListener('click', () => savePrompt().catch(e => setError(e.message)));
    document.querySelector('#btnSplit').addEventListener('click', () => doSplit().catch(e => setError(e.message)));

    ['#promptTemplate','#country','#address'].forEach(sel => {
      document.querySelector(sel).addEventListener('input', renderPromptPreview);
    });
    renderPromptPreview();

    setStatus('Ready.');
  } catch (e) {
    setError(e.message || String(e));
  }
}

window.addEventListener('DOMContentLoaded', () => { renderVersion(); init(); });
