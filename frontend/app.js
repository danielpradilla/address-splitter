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

  const headers = Object.assign({}, opts.headers || {}, {
    Authorization: `Bearer ${tokens.id_token}`,
  });

  const resp = await fetch(cfg.apiBaseUrl + path, Object.assign({}, opts, { headers }));
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
    og2.label = 'Foundation models (may require profile)';
    for (const m of models) {
      const opt = document.createElement('option');
      opt.value = m.modelId;
      opt.textContent = `${m.provider} — ${m.name}`;
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
  } catch (e) {
    const last = sessionStorage.getItem('prompt_template_last') || '';
    document.querySelector('#promptTemplate').value = last;
  }
}

async function savePrompt() {
  const tpl = document.querySelector('#promptTemplate').value;
  await apiFetch('/prompt', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_template: tpl }),
  });
  // also keep a local fallback
  sessionStorage.setItem('prompt_template_last', tpl);
  setStatus('Prompt saved.');
}

function renderPromptPreview() {
  const tpl = document.querySelector('#promptTemplate').value || '';
  const name = document.querySelector('#name').value || '';
  const country = document.querySelector('#country').value || '';
  const address = document.querySelector('#address').value || '';
  const out = tpl.replaceAll('{name}', name).replaceAll('{country}', country).replaceAll('{address}', address);
  document.querySelector('#renderedPrompt').textContent = out;
}

async function doSplit() {
  setError('');
  setStatus('Splitting…');

  const payload = {
    recipient_name: (document.querySelector('#name').value || '').trim(),
    country_code: (document.querySelector('#country').value || '').trim(),
    raw_address: (document.querySelector('#address').value || '').trim(),
    modelId: (document.querySelector('#modelId').value || '').trim(),
    pipelines: [
      document.querySelector('#p1').checked ? 'bedrock_geonames' : null,
      document.querySelector('#p2').checked ? 'libpostal_geonames' : null,
      document.querySelector('#p3').checked ? 'aws_services' : null,
    ].filter(Boolean),
  };

  if (!payload.recipient_name || !payload.raw_address) {
    throw new Error('Please fill in Name and Address.');
  }
  if (payload.pipelines.includes('bedrock_geonames') && !payload.modelId) {
    throw new Error('Select a Bedrock model for pipeline #1.');
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

function fmtPipeline(p) {
  if (!p) return '';
  const parts = [p.address_line1, [p.postcode, p.city].filter(Boolean).join(' ')].filter(Boolean);
  const loc = (p.latitude && p.longitude) ? `(${p.latitude}, ${p.longitude})` : '';
  const acc = p.geo_accuracy ? `[${p.geo_accuracy}]` : '';
  const warn = (p.warnings && p.warnings.length) ? `⚠ ${p.warnings.join('; ')}` : '';
  return [parts.join(' / '), acc, loc, warn].filter(Boolean).join(' ');
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

    const td1 = document.createElement('td');
    td1.textContent = fmtPipeline(p1);

    const td2 = document.createElement('td');
    td2.textContent = fmtPipeline(p2);

    const td3 = document.createElement('td');
    td3.textContent = fmtPipeline(p3);

    tr.appendChild(tdWhen);
    tr.appendChild(tdInp);
    tr.appendChild(td1);
    tr.appendChild(td2);
    tr.appendChild(td3);

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

    ['#promptTemplate','#name','#country','#address'].forEach(sel => {
      document.querySelector(sel).addEventListener('input', renderPromptPreview);
    });
    renderPromptPreview();

    setStatus('Ready.');
  } catch (e) {
    setError(e.message || String(e));
  }
}

window.addEventListener('DOMContentLoaded', () => { renderVersion(); init(); });
