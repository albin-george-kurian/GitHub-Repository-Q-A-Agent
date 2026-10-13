import { useEffect, useState, type FormEvent } from "react";

import { isGithubRepoUrl, repoLabel } from "../repoUrl";
import type { IndexStatus } from "../types";

interface Props {
  activeRepo: string | null;
  status: IndexStatus;
  recentRepos: string[];
  onIndex: (url: string) => void;
  onSelectRecent: (url: string) => void;
  onRemoveRecent: (url: string) => void;
}

function useElapsedSeconds(startedAt: number | null): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (startedAt === null) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [startedAt]);
  return startedAt === null ? 0 : Math.max(0, Math.floor((now - startedAt) / 1000));
}

export default function RepoPanel({ activeRepo, status, recentRepos, onIndex, onSelectRecent, onRemoveRecent }: Props) {
  const [url, setUrl] = useState(activeRepo ?? "");
  const indexing = status.kind === "indexing";
  const elapsed = useElapsedSeconds(indexing ? status.startedAt : null);

  useEffect(() => {
    if (activeRepo) setUrl(activeRepo);
  }, [activeRepo]);

  const trimmed = url.trim();
  const looksValid = isGithubRepoUrl(trimmed);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!looksValid || indexing) return;
    onIndex(trimmed);
  }

  return (
    <aside className="panel">
      <form className="repo-form" onSubmit={submit}>
        <label htmlFor="repo-url" className="field-label">
          GitHub repository
        </label>
        <div className="input-with-icon">
          <GithubIcon />
          <input
            id="repo-url"
            className="input"
            type="url"
            placeholder="https://github.com/owner/repo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={indexing}
            autoComplete="off"
            spellCheck={false}
          />
        </div>
        {trimmed && !looksValid && <p className="hint hint-warn">Enter a URL like https://github.com/owner/repo</p>}

        <button className="btn btn-primary" type="submit" disabled={!looksValid || indexing}>
          {indexing ? "Indexing…" : "Index repository"}
        </button>
      </form>

      <StatusCard status={status} elapsed={elapsed} activeRepo={activeRepo} />

      {recentRepos.length > 0 && (
        <section className="recent">
          <h2 className="section-title">Recent</h2>
          <ul>
            {recentRepos.map((repo) => (
              <li key={repo} className={repo === activeRepo ? "recent-item active" : "recent-item"}>
                <button
                  type="button"
                  className="recent-select"
                  onClick={() => onSelectRecent(repo)}
                  disabled={indexing}
                  title={repo}
                >
                  <RepoIcon />
                  <span>{repoLabel(repo)}</span>
                </button>
                <button
                  type="button"
                  className="recent-remove"
                  onClick={() => onRemoveRecent(repo)}
                  aria-label={`Remove ${repoLabel(repo)} from recent`}
                  title="Remove from list"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  );
}

function StatusCard({ status, elapsed, activeRepo }: { status: IndexStatus; elapsed: number; activeRepo: string | null }) {
  switch (status.kind) {
    case "idle":
      return null;
    case "indexing":
      return (
        <div className="status status-busy" role="status">
          <span className="spinner" aria-hidden />
          <div>
            <strong>Indexing {activeRepo ? repoLabel(activeRepo) : ""}</strong>
            <p className="hint">
              Cloning, chunking and embedding · {elapsed}s
              <br />
              Large repositories can take a few minutes.
            </p>
          </div>
        </div>
      );
    case "ready":
      return (
        <div className="status status-ok" role="status">
          <span className="dot" aria-hidden />
          <div>
            <strong>{activeRepo ? repoLabel(activeRepo) : "Ready"}</strong>
            <p className="hint">
              {status.result === null
                ? "Selected from history"
                : status.result.reused_existing
                  ? "Using existing index"
                  : `Indexed ${status.result.num_chunks ?? 0} chunks`}
            </p>
          </div>
        </div>
      );
    case "error":
      return (
        <div className="status status-err" role="alert">
          <strong>Indexing failed</strong>
          <p className="hint">{status.message}</p>
        </div>
      );
  }
}

function GithubIcon() {
  return (
    <svg className="input-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden>
      <path
        fill="currentColor"
        d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"
      />
    </svg>
  );
}

function RepoIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden className="recent-icon">
      <path
        fill="currentColor"
        d="M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z"
      />
    </svg>
  );
}
