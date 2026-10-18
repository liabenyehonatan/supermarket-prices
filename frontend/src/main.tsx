import '@fontsource-variable/rubik/wght.css';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';

// Links from before the site used plain addresses looked like "/#/product/123": open them at "/product/123".
// (Only a plain path: "#//host" or "#/\\host" would point at another site and make replaceState throw.)
if (/^#\/(?![/\\])/.test(window.location.hash)) {
  try { window.history.replaceState(null, '', window.location.hash.slice(1)); } catch { /* keep the address as it is */ }
}

const root = document.getElementById('root');
if (!root) throw new Error('Root element not found');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>
);
