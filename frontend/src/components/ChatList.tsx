import type { ChatSummary } from "../api";

interface Props {
  chats: ChatSummary[];
  activeChatId: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

const minute = 60;
const hour = 60 * minute;
const day = 24 * hour;

export function timeAgo(epochSeconds: number): string {
  const diff = Math.max(0, Date.now() / 1000 - epochSeconds);
  if (diff < minute) return "just now";
  if (diff < hour) return `${Math.floor(diff / minute)}m ago`;
  if (diff < day) return `${Math.floor(diff / hour)}h ago`;
  if (diff < 7 * day) return `${Math.floor(diff / day)}d ago`;
  return new Date(epochSeconds * 1000).toLocaleDateString();
}

export default function ChatList({ chats, activeChatId, disabled, onSelect, onNew, onDelete }: Props) {
  return (
    <section className="chats">
      <div className="section-head">
        <h2 className="section-title">Chats</h2>
        <button type="button" className="new-chat" onClick={onNew} disabled={disabled}>
          <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden>
            <path d="M8 3v10M3 8h10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
          New chat
        </button>
      </div>

      {chats.length === 0 ? (
        <p className="hint">Your conversations about this repository will appear here.</p>
      ) : (
        <ul>
          {chats.map((chat) => (
            <li key={chat.id} className={chat.id === activeChatId ? "chat-item active" : "chat-item"}>
              <button
                type="button"
                className="chat-select"
                onClick={() => onSelect(chat.id)}
                disabled={disabled}
                title={chat.title}
              >
                <span className="chat-title">{chat.title}</span>
                <span className="chat-time">{timeAgo(chat.updated_at)}</span>
              </button>
              <button
                type="button"
                className="recent-remove"
                onClick={() => onDelete(chat.id)}
                disabled={disabled}
                aria-label={`Delete chat "${chat.title}"`}
                title="Delete chat"
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
