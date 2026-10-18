import { useEffect } from 'react';

const DEFAULT_TITLE = 'סלי — חכם יותר. זול יותר.';

const META_TARGETS: Array<[selector: string, kind: 'title' | 'description']> = [
  ['meta[name="description"]', 'description'],
  ['meta[property="og:title"]', 'title'],
  ['meta[property="og:description"]', 'description'],
  ['meta[name="twitter:title"]', 'title'],
  ['meta[name="twitter:description"]', 'description'],
];

/**
 * Sets the browser tab title (and history entry name) for the page; restores the default on leave.
 * The description (and the matching link-preview tags) follow when given. The server already puts each
 * page's own tags into the HTML for search engines; this keeps them right after in-app navigation.
 */
export function useDocumentTitle(title: string | null | undefined, description?: string | null) {
  useEffect(() => {
    document.title = title || DEFAULT_TITLE;
    const restore: Array<() => void> = [];
    for (const [selector, kind] of META_TARGETS) {
      const el = document.head.querySelector<HTMLMetaElement>(selector);
      const value = kind === 'title' ? title : description;
      if (!el || !value) continue;
      const before = el.content;
      el.content = value;
      restore.push(() => { el.content = before; });
    }
    return () => { document.title = DEFAULT_TITLE; restore.forEach(fn => fn()); };
  }, [title, description]);
}

/** Tells search engines this client-rendered page is not for results (a missing page, for example). */
export function useNoIndex() {
  useEffect(() => {
    const el = document.createElement('meta');
    el.name = 'robots';
    el.content = 'noindex,follow';
    document.head.appendChild(el);
    return () => { el.remove(); };
  }, []);
}
