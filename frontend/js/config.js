export function getConfig() {
  const cfg = window.__CONFIG__;
  if (!cfg || !cfg.apiBaseUrl || !cfg.cognitoDomain || !cfg.cognitoClientId || !cfg.redirectUri) {
    throw new Error('Missing window.__CONFIG__ (config.js not loaded)');
  }
  return cfg;
}

export function qs(obj) {
  return Object.entries(obj)
    .filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
}
