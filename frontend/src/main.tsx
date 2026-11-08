import '@fontsource-variable/rubik/wght.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { reloadOnceForNewVersion } from './lib/staleChunk';

// Links from before the site used plain addresses looked like "/#/product/123": open them at "/product/123".
// (Only a plain path: "#//host" or "#/\\host" would point at another site and make replaceState throw.)
if (/^#\/(?![/\\])/.test(window.location.hash)) {
  try { window.history.replaceState(null, '', window.location.hash.slice(1)); } catch { /* keep the address as it is */ }
}

// Vite tells us when a lazy file could not be loaded (a new version replaced it).
window.addEventListener('vite:preloadError', e => { if (reloadOnceForNewVersion()) e.preventDefault(); });

const root = document.getElementById('root');
if (!root) throw new Error('Root element not found');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>
);
