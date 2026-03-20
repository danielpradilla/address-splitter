import { apiFetch } from './api.js';
import { loadRecent } from './recent-ui.js';
import { setError, setStatus } from './ui.js';

export async function doSplit() {
  setError('');
  setStatus('Splitting…');
  document.querySelector('#results').textContent =
    'Waiting for API response...\n\nYour request is being processed.';

  const payload = {
    country_code: (document.querySelector('#country').value || '').trim(),
    raw_address: (document.querySelector('#address').value || '').trim(),
    modelId: (document.querySelector('#modelId').value || '').trim(),
    pipelines: [
      document.querySelector('#p1').checked ? 'bedrock_geonames' : null,
      document.querySelector('#p2').checked ? 'libpostal_geonames' : null,
      document.querySelector('#p3').checked ? 'aws_services' : null,
      document.querySelector('#p4').checked ? 'loqate' : null,
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
