// Helpers for working with GitHub repository URLs on the client.

const GITHUB_REPO = /^https?:\/\/(www\.)?github\.com\/([\w.-]+)\/([\w.-]+?)(\.git)?\/?$/i;

export function isGithubRepoUrl(url: string): boolean {
  return GITHUB_REPO.test(url.trim());
}

/** "owner/name" for display, or the raw URL if it isn't a GitHub repo URL. */
export function repoLabel(url: string): string {
  const match = url.trim().match(GITHUB_REPO);
  return match ? `${match[2]}/${match[3]}` : url;
}

/** Link to a file in the repo's default branch, or null if the URL isn't a GitHub repo. */
export function sourceUrl(repoUrl: string, path: string): string | null {
  const match = repoUrl.trim().match(GITHUB_REPO);
  if (!match) return null;
  const encodedPath = path.split("/").map(encodeURIComponent).join("/");
  return `https://github.com/${match[2]}/${match[3]}/blob/HEAD/${encodedPath}`;
}
