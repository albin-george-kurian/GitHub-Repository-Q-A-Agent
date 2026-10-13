import type { IndexResponse } from "./api";

export type IndexStatus =
  | { kind: "idle" }
  | { kind: "indexing"; startedAt: number }
  | { kind: "ready"; result: IndexResponse | null } // null: picked from history, not re-checked
  | { kind: "error"; message: string };

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: string[];
  pending?: boolean;
  error?: boolean;
  /** Set when the backend reported the repo isn't indexed, so the UI can offer to index it. */
  notIndexed?: boolean;
  /** The rewritten, standalone question the backend searched with (follow-ups only). */
  searchedFor?: string | null;
  /** Fact stored by an explicit "remember …" message. */
  memorySaved?: string | null;
}
