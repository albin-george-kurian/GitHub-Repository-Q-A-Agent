export type IndexStatus =
  | { kind: "idle" }
  | { kind: "indexing" }
  // summary is null when the repo was picked from history rather than indexed just now
  | { kind: "ready"; summary: { numChunks: number | null; seconds: number } | null }
  | { kind: "failed"; message: string; cancelled: boolean };

/** What the backend is doing before the first words of an answer arrive. */
export type AnswerStage = "rewriting" | "searching" | "writing";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: string[];
  /** The answer is still being searched for or written (text fills in as it streams). */
  pending?: boolean;
  stage?: AnswerStage;
  /** The user stopped the answer; text holds what had arrived. */
  stopped?: boolean;
  error?: boolean;
  /** Set when the backend reported the repo isn't indexed, so the UI can offer to index it. */
  notIndexed?: boolean;
  /** The rewritten, standalone question the backend searched with (follow-ups only). */
  searchedFor?: string | null;
  /** Fact stored by an explicit "remember …" message. */
  memorySaved?: string | null;
}
