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

const USER_ID_KEY = "repo-qa:user-id";
let memoryOnlyUserId: string | null = null;

function newUserId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `u-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/** Anonymous per-browser ID that scopes chats and memories on the server (not authentication). */
export function getUserId(): string {
  try {
    let id = localStorage.getItem(USER_ID_KEY);
    if (!id) {
      id = newUserId();
      localStorage.setItem(USER_ID_KEY, id);
    }
    return id;
  } catch {
    // Storage blocked: keep one ID for this page load so the session still works.
    memoryOnlyUserId ??= newUserId();
    return memoryOnlyUserId;
  }
}
