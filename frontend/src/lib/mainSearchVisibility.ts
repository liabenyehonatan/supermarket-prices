import { useSyncExternalStore } from 'react';

// Whether the home page's own search field has scrolled out from under the header. The header shows its search
// button only then (on the home page), so there is never a second search field in sight.

let hidden = false;
const listeners = new Set<() => void>();

export function setMainSearchHidden(value: boolean) {
  if (value === hidden) return;
  hidden = value;
  listeners.forEach(l => l());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function useMainSearchHidden(): boolean {
  return useSyncExternalStore(subscribe, () => hidden);
}
