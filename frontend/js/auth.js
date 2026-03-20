import { getConfig, qs } from './config.js';

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

export function tokenStore() {
  return {
    get: () => {
      const raw = sessionStorage.getItem('tokens');
      return raw ? JSON.parse(raw) : null;
    },
    set: (t) => sessionStorage.setItem('tokens', JSON.stringify(t)),
    clear: () => sessionStorage.removeItem('tokens'),
  };
}

export async function refreshTokens() {
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
  tokenStore().set({
    ...tokens,
    ...fresh,
    refresh_token: tokens.refresh_token,
  });
}

export async function startLogin() {
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

export async function exchangeCodeForTokens(code) {
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

export function logout() {
  const cfg = getConfig();
  tokenStore().clear();
  const url = `${cfg.cognitoDomain}/logout?` + qs({
    client_id: cfg.cognitoClientId,
    logout_uri: cfg.redirectUri,
  });
  window.location.assign(url);
}

export function renderAuthState() {
  const tokens = tokenStore().get();
  document.querySelector('#authState').textContent = tokens?.id_token ? 'Signed in' : 'Signed out';
  document.querySelector('#btnLogin').style.display = tokens?.id_token ? 'none' : 'inline-block';
  document.querySelector('#btnLogout').style.display = tokens?.id_token ? 'inline-block' : 'none';
  document.querySelector('#app').style.display = tokens?.id_token ? 'block' : 'none';
}
