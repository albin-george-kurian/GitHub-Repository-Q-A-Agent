import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import Markdown from "react-markdown";

import { repoLabel, sourceUrl } from "../repoUrl";
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
        {!repoUrl && (
          <div className="empty">
            <h2>Ask questions about any public GitHub repository</h2>
            <p>Answers are grounded in the repository's own files, with links to the sources used.</p>
          </div>
        )}

        {repoUrl && messages.length === 0 && (
          <div className="empty">
            <h2>Ask about {repoLabel(repoUrl)}</h2>
            <div className="examples">
              {EXAMPLES.map((q) => (
                <button key={q} type="button" className="chip" onClick={() => send(q)} disabled={!canAsk}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m) => (
          <MessageView key={m.id} message={m} repoUrl={repoUrl} onIndexRequested={onIndexRequested} />
        ))}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={submit}>
        <textarea
          className="input composer-input"
          rows={2}
          placeholder={repoUrl ? "Ask a question… (Enter to send, Shift+Enter for a new line)" : "Index a repository first"}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          disabled={!repoUrl || disabled}
          aria-label="Question"
        />
        <button className="btn btn-primary" type="submit" disabled={!canAsk || !draft.trim()}>
          Ask
        </button>
      </form>
    </main>
  );
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
