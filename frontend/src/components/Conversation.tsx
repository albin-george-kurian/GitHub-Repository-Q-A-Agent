import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import Markdown from "react-markdown";

import { useGreeting } from "../greeting";
import { repoLabel, sourceUrl } from "../repoUrl";
import Logo from "./Logo";
import type { ChatMessage } from "../types";

interface Props {
  repoUrl: string | null;
  messages: ChatMessage[];
  disabled: boolean;
  onAsk: (question: string) => void;
  onIndexRequested: () => void;
}

const EXAMPLES = [
  "What does this project do, at a high level?",
  "Where is the main entry point?",
  "How is configuration loaded?",
  "What are the main modules and how do they interact?",
];

export default function Conversation({ repoUrl, messages, disabled, onAsk, onIndexRequested }: Props) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const greeting = useGreeting();
  const pending = messages.some((m) => m.pending);
  const canAsk = !!repoUrl && !disabled && !pending;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  function send(text: string) {
    const question = text.trim();
    if (!question || !canAsk) return;
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
      <div className="messages" aria-live="polite">
        {messages.length === 0 && (
          <div className="empty">
            <Logo size={64} className="empty-logo" />
            <h2 className="greeting">{greeting}</h2>
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
              </>
            ) : (
              <p>Point me at a public GitHub repository and ask how its code works.</p>
            )}
          </div>
        )}

        {messages.map((m) => (
          <MessageView key={m.id} message={m} repoUrl={repoUrl} onIndexRequested={onIndexRequested} />
        ))}
        <div ref={endRef} />
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
            disabled={!repoUrl || disabled}
            aria-label="Question"
          />
          <button className="send-btn" type="submit" disabled={!canAsk || !draft.trim()} aria-label="Ask" title="Ask">
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
              <path d="M3.4 20.4 21 12 3.4 3.6l.1 6.5L15 12 3.5 13.9Z" fill="currentColor" />
            </svg>
          </button>
        </div>
      </form>
    </main>
  );
}

function autoGrow(el: HTMLTextAreaElement) {
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
}

function MessageView({
  message,
  repoUrl,
  onIndexRequested,
}: {
  message: ChatMessage;
  repoUrl: string | null;
  onIndexRequested: () => void;
}) {
  if (message.role === "user") {
    return (
      <div className="msg msg-user">
        <p>{message.text}</p>
      </div>
    );
  }

  if (message.pending) {
    return (
      <div className="msg msg-assistant msg-pending" role="status">
        <span className="spinner" aria-hidden /> Searching the repository and drafting an answer…
      </div>
    );
  }

  return (
    <div className={message.error ? "msg msg-assistant msg-error" : "msg msg-assistant"}>
      {message.error ? <p>{message.text}</p> : <Markdown>{message.text}</Markdown>}

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
}
