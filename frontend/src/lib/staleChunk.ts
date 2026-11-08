/** After a deploy the old page's lazy files are gone. Reload to get the new version, but only once per minute so a
 *  real outage cannot loop. Returns whether it reloaded. */
export function reloadOnceForNewVersion(): boolean {
  try {
    const last = Number(sessionStorage.getItem('staleChunkReload') || 0);
    if (Date.now() - last < 60_000) return false;
    sessionStorage.setItem('staleChunkReload', String(Date.now()));
  } catch { /* storage blocked: reload anyway, once per page life */ }
  window.location.reload();
  return true;
}
