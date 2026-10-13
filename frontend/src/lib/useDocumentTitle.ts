import { useEffect } from 'react';

const DEFAULT_TITLE = 'סלי — חכם יותר. זול יותר.';

/** Sets the browser tab title (and history entry name) for the page; restores the default on leave. */
export function useDocumentTitle(title: string | null | undefined) {
  useEffect(() => {
    document.title = title || DEFAULT_TITLE;
    return () => { document.title = DEFAULT_TITLE; };
  }, [title]);
}
