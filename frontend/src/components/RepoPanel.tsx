import { useEffect, useState, type FormEvent } from "react";

import { isGithubRepoUrl, repoLabel } from "../repoUrl";
import type { IndexStatus } from "../types";

interface Props {
  activeRepo: string | null;
  status: IndexStatus;
  recentRepos: string[];
  onIndex: (url: string, force: boolean) => void;
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
  const [force, setForce] = useState(false);
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
    onIndex(trimmed, force);
  }

  return (
    <aside className="panel">
      <form className="repo-form" onSubmit={submit}>
        <label htmlFor="repo-url" className="field-label">
          GitHub repository
        </label>
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
        {trimmed && !looksValid && <p className="hint hint-warn">Enter a URL like https://github.com/owner/repo</p>}

        <label className="checkbox">
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} disabled={indexing} />
          Rebuild index even if one exists
        </label>

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
                  {repoLabel(repo)}
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
      return (
        <div className="status">
          <p className="hint">Index a public repository to start asking questions about its code.</p>
        </div>
      );
    case "indexing":
      return (
        <div className="status status-busy" role="status">
          <span className="spinner" aria-hidden />
          <div>
            <strong>{status.force ? "Rebuilding index" : "Indexing"}</strong>
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
