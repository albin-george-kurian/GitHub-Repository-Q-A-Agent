import { useCallback, useEffect, useRef, useState } from "react";

import { api, ApiError, type ChatSummary, type IndexJob, type Memory, type ServerMessage } from "./api";
import ChatList from "./components/ChatList";
import Conversation from "./components/Conversation";
import IndexingView from "./components/IndexingView";
import Logo from "./components/Logo";
import MemoryPanel from "./components/MemoryPanel";
import RepoPanel from "./components/RepoPanel";
import { useIndexJob } from "./hooks/useIndexJob";
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
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobSeed, setJobSeed] = useState<IndexJob | null>(null);
  const [cancelling, setCancelling] = useState(false);
  const { job, unreachable } = useIndexJob(jobId, jobSeed);

  // Identifies the conversation on screen, so late responses for a chat the user left are dropped.
  const viewKey = useRef(0);
  // Latest active repo, for async callbacks that must not apply results to a repo the user left.
  const activeRepoRef = useRef<string | null>(null);
  activeRepoRef.current = activeRepo;
  // The answer currently streaming, so Stop can abort it.
  const streamRef = useRef<AbortController | null>(null);

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

  // Always rebuilds, so answers reflect the repo's current default branch. Runs as a background
  // job on the server; useIndexJob polls it for live progress.
  const indexRepo = useCallback(
    async (url: string) => {
      openRepo(url);
      setStatus({ kind: "indexing" });
      setJobId(null);
      setJobSeed(null);
      setCancelling(false);
      try {
        const started = await api.startIndex({ repo_url: url, force_reindex: true });
        if (activeRepoRef.current !== url) return;
        setJobSeed(started);
        setJobId(started.id);
        setBackendDown(false);
      } catch (err) {
        setStatus({ kind: "failed", message: err instanceof Error ? err.message : String(err), cancelled: false });
        noteNetworkError(err);
      }
    },
    [openRepo, noteNetworkError],
  );

  // Turn the job's final state into the app's status.
  useEffect(() => {
    if (!job || status.kind !== "indexing") return;
    if (job.status === "done") {
      setStatus({ kind: "ready", summary: { numChunks: job.num_chunks, seconds: job.elapsed } });
      setRecentRepos((prev) => saveRecentRepo(activeRepoRef.current ?? job.repo_url, prev));
    } else if (job.status === "error") {
      setStatus({ kind: "failed", message: job.error ?? "Indexing failed", cancelled: false });
    } else if (job.status === "cancelled") {
      setStatus({ kind: "failed", message: "Indexing was cancelled.", cancelled: true });
    }
  }, [job, status.kind]);

  useEffect(() => {
    if (unreachable) setBackendDown(true);
  }, [unreachable]);

  const cancelIndex = useCallback(async () => {
    if (!jobId) return;
    setCancelling(true);
    try {
      await api.cancelIndexJob(jobId);
    } catch (err) {
      setCancelling(false);
      noteNetworkError(err);
    }
  }, [jobId, noteNetworkError]);

  const selectRecent = useCallback(
    (url: string) => {
      openRepo(url);
      setJobId(null);
      setStatus({ kind: "ready", summary: null });
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
      const controller = new AbortController();
      streamRef.current = controller;
      setMessages((msgs) => [
        ...msgs,
        { id: newId(), role: "user", text: question },
        { id: pendingId, role: "assistant", text: "", pending: true },
      ]);

      // Updates to the reply are dropped once the user has moved to another chat; the server still
      // finishes and saves the answer there.
      const update = (change: (m: ChatMessage) => ChatMessage) => {
        if (key === viewKey.current) setMessages((msgs) => msgs.map((m) => (m.id === pendingId ? change(m) : m)));
      };
      // Words arrive faster than the screen refreshes, so render at most once per frame.
      let text = "";
      let frame = 0;
      const flush = () => {
        frame = 0;
        update((m) => ({ ...m, text }));
      };

      try {
        const res = await api.queryStream(
          { repo_url: repo, question, chat_id: activeChatId },
          (event) => {
            if (event.type === "start") {
              if (key === viewKey.current) setActiveChatId(event.chat_id);
            } else if (event.type === "status") {
              update((m) => ({ ...m, stage: event.stage }));
            } else if (event.type === "sources") {
              update((m) => ({ ...m, stage: "writing", sources: event.sources, searchedFor: event.standalone_question }));
            } else {
              text += event.text;
              frame ||= requestAnimationFrame(flush);
            }
          },
          controller.signal,
        );
        cancelAnimationFrame(frame);
        update(() => ({
          id: pendingId,
          role: "assistant",
          text: res.answer,
          sources: res.sources,
          searchedFor: res.standalone_question,
          memorySaved: res.memory_saved,
        }));
        if (key === viewKey.current) setActiveChatId(res.chat_id);
        refreshChats(repo);
        // Preferences are learned in the background after the reply; pick them up shortly after.
        if (res.memory_saved) refreshMemories();
        else window.setTimeout(refreshMemories, 4000);
      } catch (err) {
        cancelAnimationFrame(frame);
        if (controller.signal.aborted) {
          // Stopped: keep what arrived. The server saved the same text, so the chat stays in sync.
          update((m) => ({ ...m, text, pending: false, stage: undefined, stopped: true }));
          refreshChats(repo);
        } else {
          update(() => ({
            id: pendingId,
            role: "assistant",
            text: err instanceof Error ? err.message : String(err),
            error: true,
            notIndexed: err instanceof ApiError && err.code === "repo_not_indexed",
          }));
          noteNetworkError(err);
        }
      } finally {
        if (streamRef.current === controller) streamRef.current = null;
      }
    },
    [activeRepo, activeChatId, refreshChats, refreshMemories, noteNetworkError],
  );

  const stopAnswer = useCallback(() => streamRef.current?.abort(), []);
  const reindexActive = useCallback(() => {
    if (activeRepo) indexRepo(activeRepo);
  }, [activeRepo, indexRepo]);

  const closeMemory = useCallback(() => setMemoryOpen(false), []);
  const openMemory = useCallback(() => setMemoryOpen(true), []);

  const chatRepo = status.kind === "ready" ? activeRepo : null;
  const showIndexing = !!activeRepo && (status.kind === "indexing" || status.kind === "failed");
  const pending = messages.some((m) => m.pending);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <Logo size={26} />
          <h1>Repo Q&amp;A</h1>
        </div>
        <p className="tagline">Grounded answers about any public GitHub repository</p>
        <button
          type="button"
          className="memory-btn"
          onClick={openMemory}
          aria-label={`Memory, ${memories.length} item${memories.length === 1 ? "" : "s"}`}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
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
          job={status.kind === "indexing" ? job : null}
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
        {showIndexing && activeRepo ? (
          <IndexingView
            repoUrl={activeRepo}
            job={job}
            failure={status.kind === "failed" ? { message: status.message, cancelled: status.cancelled } : null}
            cancelling={cancelling}
            onCancel={cancelIndex}
            onRetry={reindexActive}
          />
        ) : (
          <Conversation
            repoUrl={chatRepo}
            messages={messages}
            readySummary={status.kind === "ready" ? status.summary : null}
            onAsk={ask}
            onStop={stopAnswer}
            onIndexRequested={reindexActive}
            onOpenMemory={openMemory}
          />
        )}
      </div>

      <MemoryPanel open={memoryOpen} memories={memories} onClose={closeMemory} onChange={setMemories} />
    </div>
  );
}
