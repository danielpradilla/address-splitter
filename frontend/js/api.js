import { getConfig } from './config.js';
import { refreshTokens, tokenStore } from './auth.js';
import { setStatus } from './ui.js';

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const SERVICE_BY_PATH = [
  [/^\/models\b/, 'Bedrock model list'],
  [/^\/prompt\b/, 'Prompt and pricing settings'],
  [/^\/recent\b/, 'Recent submissions'],
  [/^\/submission\b/, 'Submission history'],
  [/^\/batch-jobs\b/, 'Batch jobs'],
  [/^\/split\b/, 'Address splitting API'],
];

const PIPELINE_LABELS = {
  bedrock_geonames: 'Bedrock + GeoNames',
  libpostal_geonames: 'libpostal + GeoNames',
  aws_services: 'AWS services / Amazon Location',
  loqate: 'Loqate',
};

function serviceNameFor(path) {
  return SERVICE_BY_PATH.find(([pattern]) => pattern.test(path))?.[1] || 'API';
}

function requestedPipelines(opts) {
  if (!opts.body || typeof opts.body !== 'string') return [];
  try {
    const body = JSON.parse(opts.body);
    return (body.pipelines || []).map((name) => PIPELINE_LABELS[name] || name);
  } catch {
    return [];
  }
}

function apiErrorMessage({ path, opts, status, data }) {
  const serviceName = opts.serviceName || serviceNameFor(path);
  const detail = data?.message || data?.error || data?.raw || `HTTP ${status}`;
  const pipelines = requestedPipelines(opts);

  if (status === 503) {
    const suffix = pipelines.length ? ` Requested pipelines: ${pipelines.join(', ')}.` : '';
    return `${serviceName} is unavailable.${suffix} Detail: ${detail}`;
  }
  if ([500, 502, 504].includes(status)) {
    const suffix = pipelines.length ? ` Requested pipelines: ${pipelines.join(', ')}.` : '';
    return `${serviceName} failed while calling the backend.${suffix} Detail: ${detail}`;
  }
  return `${serviceName} request failed. Detail: ${detail}`;
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
      throw new Error(apiErrorMessage({ path, opts, status: resp.status, data }));
    }
    return data;
  }
}
