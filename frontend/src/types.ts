export type IndexStatus =
  | { kind: "idle" }
  | { kind: "indexing" }
  // summary is null when the repo was picked from history rather than indexed just now
  | { kind: "ready"; summary: { numChunks: number | null; seconds: number } | null }
  | { kind: "failed"; message: string; cancelled: boolean };

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
