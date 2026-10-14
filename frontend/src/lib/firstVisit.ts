// "Show this only the first time": the flag lives in localStorage, so it survives closing the app. Blocked storage means
// the person is never nagged (nothing is shown).

export function hasSeen(key: string): boolean {
  try { return localStorage.getItem(key) !== null; } catch { return true; }
}

export function markSeen(key: string): void {
  try { localStorage.setItem(key, '1'); } catch { /* storage blocked: nothing to remember */ }
}
