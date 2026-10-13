import { useEffect, useRef, useState, type FormEvent } from "react";

import { api, type Memory } from "../api";

interface Props {
  open: boolean;
  memories: Memory[];
  onClose: () => void;
  onChange: (memories: Memory[]) => void;
}

export default function MemoryPanel({ open, memories, onClose, onChange }: Props) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    setError(null);
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function run(action: () => Promise<Memory[]>) {
    setBusy(true);
    setError(null);
    try {
      onChange(await action());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  function add(e: FormEvent) {
    e.preventDefault();
    const content = draft.trim();
    if (content.length < 3) return;
    void run(async () => {
      const created = await api.addMemory(content);
      setDraft("");
      return [...memories, created];
    });
  }

  const remove = (id: string) =>
    run(async () => {
      await api.deleteMemory(id);
      return memories.filter((m) => m.id !== id);
    });

  const clearAll = () => {
    if (!window.confirm("Forget everything Repo Q&A remembers about you?")) return;
    void run(async () => {
      await api.clearMemories();
      return [];
    });
  };

  return (
    <div className="drawer-backdrop" onClick={onClose}>
      <aside
        className="drawer"
        role="dialog"
        aria-modal="true"
        aria-labelledby="memory-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="drawer-head">
          <div>
            <h2 id="memory-title">Memory</h2>
            <p className="hint">
              Used in every chat to tailor answers. Say <code>remember that …</code> in a chat, or add one here.
            </p>
          </div>
          <button ref={closeRef} type="button" className="icon-btn" onClick={onClose} aria-label="Close memory">
            ×
          </button>
        </header>

        <form className="memory-form" onSubmit={add}>
          <input
            className="input"
            placeholder="e.g. I prefer short answers with code examples"
            value={draft}
            maxLength={300}
            onChange={(e) => setDraft(e.target.value)}
            disabled={busy}
          />
          <button className="btn btn-primary" type="submit" disabled={busy || draft.trim().length < 3}>
            Add
          </button>
        </form>
        {error && <p className="hint hint-err">{error}</p>}

        {memories.length === 0 ? (
          <div className="memory-empty">
            <p>Nothing remembered yet.</p>
            <p className="hint">Mention your experience or how you like answers, and it will be picked up.</p>
          </div>
        ) : (
          <ul className="memory-list">
            {memories.map((m) => (
              <li key={m.id} className="memory-item">
                <span className={m.source === "auto" ? "memory-tag tag-auto" : "memory-tag"}>
                  {m.source === "auto" ? "Learned" : "Saved"}
                </span>
                <span className="memory-text">{m.content}</span>
                <button
                  type="button"
                  className="icon-btn"
                  onClick={() => void remove(m.id)}
                  disabled={busy}
                  aria-label={`Forget "${m.content}"`}
                  title="Forget"
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}

        {memories.length > 0 && (
          <button type="button" className="btn btn-danger" onClick={clearAll} disabled={busy}>
            Forget everything
          </button>
        )}
      </aside>
    </div>
  );
}
