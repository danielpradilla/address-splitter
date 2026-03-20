import { getConfig } from './config.js';

export function setStatus(msg) {
  const el = document.querySelector('#status');
  if (el) el.textContent = msg;
}

export function setError(msg) {
  const el = document.querySelector('#error');
  if (el) {
    el.textContent = msg;
    el.style.display = msg ? 'block' : 'none';
  }
}

export function renderVersion() {
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
