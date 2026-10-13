import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, type ChatSummary, type Memory, type ServerMessage } from "./api";
import ChatList from "./components/ChatList";
import Conversation from "./components/Conversation";
import Logo from "./components/Logo";
import MemoryPanel from "./components/MemoryPanel";
import RepoPanel from "./components/RepoPanel";
import { loadRecentRepos, removeRecentRepo, saveRecentRepo } from "./storage";
import type { ChatMessage, IndexStatus } from "./types";

let nextId = 0;
const newId = () => `local-${++nextId}`;

function fromServer(messages: ServerMessage[]): ChatMessage[] {
  return messages.map((m, i) => {
    // Like live replies, only show the rewritten search when it differs from what was asked.
    const asked = messages[i - 1]?.role === "user" ? messages[i - 1].content : null;
    const rewritten = m.role === "assistant" && m.standalone_question !== asked ? m.standalone_question : null;
    return { id: String(m.id), role: m.role, text: m.content, sources: m.sources, searchedFor: rewritten };
  });
}

export default function App() {
  const [activeRepo, setActiveRepo] = useState<string | null>(null);
  const [status, setStatus] = useState<IndexStatus>({ kind: "idle" });
  const [recentRepos, setRecentRepos] = useState<string[]>(loadRecentRepos);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [activeChatId, setActiveChatId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [memoryOpen, setMemoryOpen] = useState(false);
  const [backendDown, setBackendDown] = useState(false);

  // Identifies the conversation on screen, so late responses for a chat the user left are dropped.
  const viewKey = useRef(0);
  // Latest active repo, for async callbacks that must not apply results to a repo the user left.
  const activeRepoRef = useRef<string | null>(null);
  activeRepoRef.current = activeRepo;

  const noteNetworkError = useCallback((err: unknown) => {
    if (err instanceof ApiError && err.status === 0) setBackendDown(true);
  }, []);

  const refreshMemories = useCallback(() => {
    api.listMemories().then(setMemories, noteNetworkError);
  }, [noteNetworkError]);

  useEffect(() => {
    api.health().then(
      () => {
        setBackendDown(false);
        refreshMemories();
      },
      () => setBackendDown(true),
    );
  }, [refreshMemories]);

  const refreshChats = useCallback(
    (repo: string) => {
      api.listChats(repo).then((list) => {
        setChats((prev) => (repo === activeRepoRef.current ? list : prev));
      }, noteNetworkError);
    },
    [noteNetworkError],
  );
  const openRepo = useCallback(
    (repo: string) => {
      viewKey.current++;
      setActiveRepo(repo);
      activeRepoRef.current = repo;
      setActiveChatId(null);
      setMessages([]);
      setChats([]);
      refreshChats(repo);
    },
    [refreshChats],
  );

  // Always rebuilds, so answers reflect the repo's current default branch.
  const indexRepo = useCallback(
    async (url: string) => {
      openRepo(url);
      setStatus({ kind: "indexing", startedAt: Date.now() });
      try {
        const result = await api.index({ repo_url: url, force_reindex: true });
        setStatus({ kind: "ready", result });
        setRecentRepos((prev) => saveRecentRepo(url, prev));
        setBackendDown(false);
      } catch (err) {
        setStatus({ kind: "error", message: err instanceof Error ? err.message : String(err) });
        noteNetworkError(err);
      }
    },
    [openRepo, noteNetworkError],
  );

  const selectRecent = useCallback(
    (url: string) => {
      openRepo(url);
      setStatus({ kind: "ready", result: null });
    },
    [openRepo],
  );

  const removeRecent = useCallback((url: string) => {
    setRecentRepos((prev) => removeRecentRepo(url, prev));
  }, []);

  const newChat = useCallback(() => {
    viewKey.current++;
    setActiveChatId(null);
    setMessages([]);
  }, []);

  const selectChat = useCallback(
    async (id: string) => {
      const key = ++viewKey.current;
      setActiveChatId(id);
      setMessages([]);
      try {
        const detail = await api.getChat(id);
        if (key === viewKey.current) setMessages(fromServer(detail.messages));
      } catch (err) {
        noteNetworkError(err);
        if (key === viewKey.current) {
          setMessages([{ id: newId(), role: "assistant", text: (err as Error).message, error: true }]);
        }
      }
    },
    [noteNetworkError],
  );

  const deleteChat = useCallback(
    async (id: string) => {
      try {
        await api.deleteChat(id);
      } catch (err) {
        noteNetworkError(err);
        return;
      }
      setChats((prev) => prev.filter((c) => c.id !== id));
      if (id === activeChatId) newChat();
    },
    [activeChatId, newChat, noteNetworkError],
  );

  const ask = useCallback(
    async (question: string) => {
      if (!activeRepo) return;
      const repo = activeRepo;
      const key = viewKey.current;
      const pendingId = newId();
      setMessages((msgs) => [
        ...msgs,
        { id: newId(), role: "user", text: question },
        { id: pendingId, role: "assistant", text: "", pending: true },
      ]);

      let reply: ChatMessage;
      try {
        const res = await api.query({ repo_url: repo, question, chat_id: activeChatId });
        reply = {
          id: pendingId,
          role: "assistant",
          text: res.answer,
          sources: res.sources,
          searchedFor: res.standalone_question,
          memorySaved: res.memory_saved,
        };
        if (key === viewKey.current) setActiveChatId(res.chat_id);
        refreshChats(repo);
        // Preferences are learned in the background after the reply; pick them up shortly after.
        if (res.memory_saved) refreshMemories();
        else window.setTimeout(refreshMemories, 4000);
      } catch (err) {
        reply = {
          id: pendingId,
          role: "assistant",
          text: err instanceof Error ? err.message : String(err),
          error: true,
          notIndexed: err instanceof ApiError && err.code === "repo_not_indexed",
        };
        noteNetworkError(err);
      }
      if (key === viewKey.current) {
        setMessages((msgs) => msgs.map((m) => (m.id === pendingId ? reply : m)));
      }
    },
    [activeRepo, activeChatId, refreshChats, refreshMemories, noteNetworkError],
  );

  const closeMemory = useCallback(() => setMemoryOpen(false), []);
  const openMemory = useCallback(() => setMemoryOpen(true), []);

  const chatRepo = status.kind === "ready" || status.kind === "indexing" ? activeRepo : null;
  const pending = messages.some((m) => m.pending);

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
        <button
          type="button"
          className="memory-btn"
          onClick={openMemory}
          aria-label={`Memory, ${memories.length} item${memories.length === 1 ? "" : "s"}`}
        >
          <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
            <path
              d="M9.5 3a3.5 3.5 0 0 0-3.4 4.3A3.5 3.5 0 0 0 4 13.5a3.5 3.5 0 0 0 2.5 5.4A3 3 0 0 0 12 20V4.6A3.5 3.5 0 0 0 9.5 3Zm5 0A3.5 3.5 0 0 0 12 4.6V20a3 3 0 0 0 5.5-1.1 3.5 3.5 0 0 0 2.5-5.4 3.5 3.5 0 0 0-2.1-6.2A3.5 3.5 0 0 0 14.5 3Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
          </svg>
          Memory
          {memories.length > 0 && <span className="count">{memories.length}</span>}
        </button>
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
        >
          {status.kind === "ready" && (
            <ChatList
              chats={chats}
              activeChatId={activeChatId}
              disabled={pending}
              onSelect={selectChat}
              onNew={newChat}
              onDelete={deleteChat}
            />
          )}
        </RepoPanel>
        <Conversation
          repoUrl={chatRepo}
          messages={messages}
          disabled={status.kind === "indexing"}
          onAsk={ask}
          onIndexRequested={() => activeRepo && indexRepo(activeRepo)}
          onOpenMemory={openMemory}
        />
      </div>

      <MemoryPanel open={memoryOpen} memories={memories} onClose={closeMemory} onChange={setMemories} />
    </div>
  );
}
