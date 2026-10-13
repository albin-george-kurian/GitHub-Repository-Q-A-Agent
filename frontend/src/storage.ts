// Per-browser convenience storage. Every access is guarded: storage can be
// unavailable (private mode, blocked site data) and the app must still work.

const RECENT_KEY = "repo-qa:recent-repos";
const MAX_RECENT = 8;

export function loadRecentRepos(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function saveRecentRepo(url: string, current: string[]): string[] {
  const next = [url, ...current.filter((u) => u !== url)].slice(0, MAX_RECENT);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // ignore: recents are a nicety
  }
  return next;
}

export function removeRecentRepo(url: string, current: string[]): string[] {
  const next = current.filter((u) => u !== url);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // ignore
  }
  return next;
}
