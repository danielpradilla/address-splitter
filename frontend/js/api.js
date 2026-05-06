import { getConfig } from './config.js';
import { refreshTokens, tokenStore } from './auth.js';
import { setStatus } from './ui.js';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function apiFetch(path, opts = {}) {
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

  const maxAttempts = 12;
  const retryableStatuses = new Set([500, 502, 503, 504]);
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    let resp = await doReq();
    if (resp.status === 401) {
      await refreshTokens();
      resp = await doReq();
    }
    if (retryableStatuses.has(resp.status) && attempt < maxAttempts) {
      setStatus(`Starting… (warming up) [${attempt}/${maxAttempts - 1}]`);
      await sleep(Math.min(2000 * attempt, 15000));
      continue;
    }
    const text = await resp.text();
    let data;
    try { data = text ? JSON.parse(text) : null; } catch { data = { raw: text }; }
    if (!resp.ok) {
      throw new Error(data?.message || data?.error || `API error ${resp.status}`);
    }
    return data;
  }
}
