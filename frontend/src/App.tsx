import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "./api";
import Conversation from "./components/Conversation";
import Logo from "./components/Logo";
import RepoPanel from "./components/RepoPanel";
import { loadRecentRepos, removeRecentRepo, saveRecentRepo } from "./storage";
import type { ChatMessage, IndexStatus } from "./types";

let nextId = 0;
const newId = () => `m${++nextId}`;

export default function App() {
  const [activeRepo, setActiveRepo] = useState<string | null>(null);
  const [status, setStatus] = useState<IndexStatus>({ kind: "idle" });
  const [recentRepos, setRecentRepos] = useState<string[]>(loadRecentRepos);
  // Conversations are kept per repo so switching back and forth keeps history for the session.
  const [threads, setThreads] = useState<Record<string, ChatMessage[]>>({});
  const [backendDown, setBackendDown] = useState(false);

  useEffect(() => {
    api.health().then(
      () => setBackendDown(false),
      () => setBackendDown(true),
    );
  }, []);

  const updateThread = useCallback((repo: string, fn: (msgs: ChatMessage[]) => ChatMessage[]) => {
    setThreads((prev) => ({ ...prev, [repo]: fn(prev[repo] ?? []) }));
  }, []);

  // Always rebuilds, so answers reflect the repo's current default branch.
  const indexRepo = useCallback(async (url: string) => {
    setActiveRepo(url);
    setStatus({ kind: "indexing", startedAt: Date.now() });
    try {
      const result = await api.index({ repo_url: url, force_reindex: true });
      setStatus({ kind: "ready", result });
      setRecentRepos((prev) => saveRecentRepo(url, prev));
      setBackendDown(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setStatus({ kind: "error", message });
      if (err instanceof ApiError && err.status === 0) setBackendDown(true);
    }
  }, []);

  const ask = useCallback(
    async (question: string) => {
      if (!activeRepo) return;
      const repo = activeRepo;
      const pendingId = newId();
      updateThread(repo, (msgs) => [
        ...msgs,
        { id: newId(), role: "user", text: question },
        { id: pendingId, role: "assistant", text: "", pending: true },
      ]);

      let reply: ChatMessage;
      try {
        const res = await api.query({ repo_url: repo, question });
        reply = { id: pendingId, role: "assistant", text: res.answer, sources: res.sources };
      } catch (err) {
        const notIndexed = err instanceof ApiError && err.status === 404;
        reply = {
          id: pendingId,
          role: "assistant",
          text: err instanceof Error ? err.message : String(err),
          error: true,
          notIndexed,
        };
        if (err instanceof ApiError && err.status === 0) setBackendDown(true);
      }
      updateThread(repo, (msgs) => msgs.map((m) => (m.id === pendingId ? reply : m)));
    },
    [activeRepo, updateThread],
  );

  const selectRecent = useCallback((url: string) => {
    setActiveRepo(url);
    setStatus({ kind: "ready", result: null });
  }, []);

  const removeRecent = useCallback((url: string) => {
    setRecentRepos((prev) => removeRecentRepo(url, prev));
  }, []);

  const messages = activeRepo ? (threads[activeRepo] ?? []) : [];
  const chatRepo = status.kind === "ready" || status.kind === "indexing" ? activeRepo : null;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <Logo size={30} />
          <h1>
            Repo <span className="brand-accent">Q&amp;A</span>
          </h1>
        </div>
        <p className="tagline">Grounded answers about any public GitHub repository</p>
      </header>

      {backendDown && (
        <div className="banner" role="alert">
          Can't reach the API. Start it with <code>uvicorn src.api.main:app --reload</code> from the project root.
        </div>
      )}

      <div className="layout">
        <RepoPanel
          activeRepo={activeRepo}
          status={status}
          recentRepos={recentRepos}
          onIndex={indexRepo}
          onSelectRecent={selectRecent}
          onRemoveRecent={removeRecent}
        />
        <Conversation
          repoUrl={chatRepo}
          messages={messages}
          disabled={status.kind === "indexing"}
          onAsk={ask}
          onIndexRequested={() => activeRepo && indexRepo(activeRepo)}
        />
      </div>
    </div>
  );
}
