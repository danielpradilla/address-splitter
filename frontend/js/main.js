import { exchangeCodeForTokens, logout, renderAuthState, startLogin, tokenStore } from './auth.js';
import { loadPrompt, loadModels, loadCountries, renderPromptPreview, savePrompt } from './prompt-ui.js';
import { loadRecent } from './recent-ui.js';
import { doSplit } from './split-ui.js';
import { renderVersion, setError, setStatus } from './ui.js';

async function init() {
  try {
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
      url.searchParams.delete('code');
      url.searchParams.delete('state');
      window.history.replaceState({}, document.title, url.toString());
    }

    renderAuthState();

    document.querySelector('#btnLogin').addEventListener('click', () => startLogin().catch((e) => setError(e.message)));
    document.querySelector('#btnLogout').addEventListener('click', () => logout());

    if (tokenStore().get()?.id_token) {
      await loadCountries();
      await loadModels();
      await loadPrompt();
      await loadRecent();
    }

    document.querySelector('#btnSavePrompt').addEventListener('click', () => savePrompt().catch((e) => setError(e.message)));
    document.querySelector('#btnSplit').addEventListener('click', () => doSplit().catch((e) => setError(e.message)));

    ['#promptTemplate', '#country', '#address'].forEach((sel) => {
      document.querySelector(sel).addEventListener('input', renderPromptPreview);
    });
    renderPromptPreview();

    setStatus('Ready.');
  } catch (e) {
    setError(e.message || String(e));
  }
}

window.addEventListener('DOMContentLoaded', () => {
  renderVersion();
  init();
});
