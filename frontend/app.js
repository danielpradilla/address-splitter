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
  sel.innerHTML = '<option value="">(select a model)</option>';
  for (const m of data.models || []) {
    const opt = document.createElement('option');
    opt.value = m.modelId;
    opt.textContent = `${m.provider} — ${m.name}`;
    sel.appendChild(opt);
  }
}

async function loadPrompt() {
  const data = await apiFetch('/prompt');
  document.querySelector('#promptTemplate').value = data.prompt_template || '';
}

async function savePrompt() {
  const tpl = document.querySelector('#promptTemplate').value;
  await apiFetch('/prompt', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt_template: tpl }),
  });
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
    recipient_name: document.querySelector('#name').value,
    country_code: document.querySelector('#country').value,
    raw_address: document.querySelector('#address').value,
    modelId: document.querySelector('#modelId').value,
    pipelines: [
      document.querySelector('#p1').checked ? 'bedrock_geonames' : null,
      document.querySelector('#p2').checked ? 'libpostal_geonames' : null,
      document.querySelector('#p3').checked ? 'aws_services' : null,
    ].filter(Boolean),
  };

  const data = await apiFetch('/split', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  document.querySelector('#results').textContent = JSON.stringify(data, null, 2);
  setStatus('Done.');
  await loadRecent();
}

async function loadRecent() {
  const data = await apiFetch('/recent?limit=10');
  const ul = document.querySelector('#recent');
  ul.innerHTML = '';
  for (const it of data.items || []) {
    const li = document.createElement('li');
    li.textContent = `${it.created_at} — ${it.raw_address_preview} (${it.preferred_method || 'no preferred'})`;
    ul.appendChild(li);
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

window.addEventListener('DOMContentLoaded', init);
