import { memo, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import Markdown, { type Components } from "react-markdown";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

import { useGreeting } from "../greeting";
import { formatDuration } from "../languages";
import { repoLabel, sourceUrl } from "../repoUrl";
import Logo from "./Logo";
import type { ChatMessage } from "../types";

interface Props {
  repoUrl: string | null;
  messages: ChatMessage[];
  /** Shown under the greeting right after indexing finishes. */
  readySummary: { numChunks: number | null; seconds: number } | null;
  onAsk: (question: string) => void;
  /** Stops the answer that is streaming in. */
  onStop: () => void;
  onIndexRequested: () => void;
  onOpenMemory: () => void;
}

/** Keep following new text only while the reader is (nearly) at the bottom. */
const STICK_THRESHOLD_PX = 80;

// GitHub-flavoured Markdown (tables, task lists, strikethrough). Models sometimes put HTML such as
// <br> or lists inside table cells; it is rendered only after sanitizing, because answers quote
// untrusted repository content.
const REMARK_PLUGINS = [remarkGfm];
const REHYPE_PLUGINS = [rehypeRaw, rehypeSanitize];
const MARKDOWN_COMPONENTS: Components = {
  // Wide tables scroll sideways instead of stretching the conversation.
  table: ({ node: _node, ...props }) => (
    <div className="table-wrap">
      <table {...props} />
    </div>
  ),
  // Images become links rather than loading on their own: repository text can steer the model, and an
  // image URL it writes would otherwise be fetched (and could carry data out) without a click.
  img: ({ src, alt }) =>
    src ? (
      <a href={src} target="_blank" rel="noreferrer noopener">
        {alt || "image"}
      </a>
    ) : null,
};

const EXAMPLES = [
  "What does this project do, at a high level?",
  "Where is the main entry point?",
  "How is configuration loaded?",
  "What are the main modules and how do they interact?",
];

export default function Conversation({
  repoUrl,
  messages,
  readySummary,
  onAsk,
  onStop,
  onIndexRequested,
  onOpenMemory,
}: Props) {
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const greeting = useGreeting();
  const pending = messages.some((m) => m.pending);
  const canAsk = !!repoUrl && !pending;

  // Follow the answer as it streams in, unless the reader has scrolled up to read something.
  useEffect(() => {
    const list = listRef.current;
    if (list && stickToBottom.current) list.scrollTop = list.scrollHeight;
  }, [messages]);

  function onScroll() {
    const list = listRef.current;
    if (list) stickToBottom.current = list.scrollHeight - list.scrollTop - list.clientHeight < STICK_THRESHOLD_PX;
  }

  function send(text: string) {
    const question = text.trim();
    if (!question || !canAsk) return;
    stickToBottom.current = true;
    onAsk(question);
    setDraft("");
    if (inputRef.current) inputRef.current.style.height = "";
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    send(draft);
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send(draft);
    }
  }

  return (
    <main className="conversation">
      <div className="messages" ref={listRef} onScroll={onScroll} aria-live="polite" aria-busy={pending}>
        {messages.length === 0 && (
          <div className="empty">
            <Logo size={40} className="empty-logo" />
            <h2 className="greeting">{greeting}</h2>
            {repoUrl && readySummary && (
              <p className="ready-line">
                <span className="dot" aria-hidden /> Indexed {readySummary.numChunks?.toLocaleString() ?? 0} chunks in{" "}
                {formatDuration(readySummary.seconds)}
              </p>
            )}
            {repoUrl ? (
              <>
                <p>
                  Ask anything about <code className="repo-pill">{repoLabel(repoUrl)}</code>. Answers are grounded in
                  its files, with links to the sources.
                </p>
                <div className="examples">
                  {EXAMPLES.map((q) => (
                    <button key={q} type="button" className="chip" onClick={() => send(q)} disabled={!canAsk}>
                      {q}
                    </button>
                  ))}
                </div>
                <p className="tip">
                  Follow-up questions keep context. Say <code>remember that …</code> to teach me how you like answers.
                </p>
              </>
            ) : (
              <p>Point me at a public GitHub repository and ask how its code works.</p>
            )}
          </div>
        )}

        {messages.map((m) => (
          <MessageView
            key={m.id}
            message={m}
            repoUrl={repoUrl}
            onIndexRequested={onIndexRequested}
            onOpenMemory={onOpenMemory}
          />
        ))}
      </div>

      <form className="composer" onSubmit={submit}>
        <div className="composer-box">
          <textarea
            ref={inputRef}
            className="composer-input"
            rows={1}
            placeholder={repoUrl ? "Ask a question… (Enter to send, Shift+Enter for a new line)" : "Index a repository first"}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              autoGrow(e.target);
            }}
            onKeyDown={onKeyDown}
            disabled={!repoUrl}
            aria-label="Question"
          />
          {pending ? (
            <button className="send-btn stop" type="button" onClick={onStop} aria-label="Stop answering" title="Stop">
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
                <rect x="6.5" y="6.5" width="11" height="11" rx="2" fill="currentColor" />
              </svg>
            </button>
          ) : (
            <button className="send-btn" type="submit" disabled={!canAsk || !draft.trim()} aria-label="Ask" title="Ask">
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
                <path d="M3.4 20.4 21 12 3.4 3.6l.1 6.5L15 12 3.5 13.9Z" fill="currentColor" />
              </svg>
            </button>
          )}
        </div>
      </form>
    </main>
  );
}

function autoGrow(el: HTMLTextAreaElement) {
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
}

function pendingLabel(message: ChatMessage): string {
  if (message.stage === "rewriting") return "Understanding your follow-up…";
  if (message.stage === "writing") {
    const files = message.sources?.length ?? 0;
    return files ? `Reading ${files} file${files === 1 ? "" : "s"}…` : "Writing the answer…";
  }
  return "Searching the code…";
}

// Memoized: while an answer streams, only that message re-renders (and re-parses its Markdown).
const MessageView = memo(function MessageView({
  message,
  repoUrl,
  onIndexRequested,
  onOpenMemory,
}: {
  message: ChatMessage;
  repoUrl: string | null;
  onIndexRequested: () => void;
  onOpenMemory: () => void;
}) {
  if (message.role === "user") {
    return (
      <div className="msg msg-user">
        <p>{message.text}</p>
      </div>
    );
  }

  // Before the first words arrive, say what is happening.
  if (message.pending && !message.text) {
    return (
      <div className="msg msg-assistant msg-pending" role="status">
        <span className="spinner" aria-hidden /> {pendingLabel(message)}
      </div>
    );
  }

  const className = ["msg", "msg-assistant", message.error && "msg-error", message.pending && "msg-streaming"]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={className}>
      {message.searchedFor && (
        <p className="searched-for" title="Your follow-up was rewritten using the conversation before searching">
          Searched for: {message.searchedFor}
        </p>
      )}
      {message.error ? (
        <p>{message.text}</p>
      ) : (
        <div className="md">
          <Markdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS} components={MARKDOWN_COMPONENTS}>
            {message.text}
          </Markdown>
        </div>
      )}

      {message.stopped && (
        <p className="stopped-note">{message.text ? "Stopped" : "Stopped before answering"}</p>
      )}

      {message.memorySaved && (
        <button type="button" className="memory-badge" onClick={onOpenMemory}>
          Saved to memory · View
        </button>
      )}

      {message.notIndexed && (
        <button type="button" className="btn btn-secondary" onClick={onIndexRequested}>
          Index this repository now
        </button>
      )}

      {message.sources && message.sources.length > 0 && (
        <div className="sources">
          <span className="sources-label">Sources</span>
          <ul>
            {message.sources.map((path) => {
              const href = repoUrl ? sourceUrl(repoUrl, path) : null;
              return (
                <li key={path}>
                  {href ? (
                    <a href={href} target="_blank" rel="noreferrer noopener">
                      {path}
                    </a>
                  ) : (
                    <code>{path}</code>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
});
