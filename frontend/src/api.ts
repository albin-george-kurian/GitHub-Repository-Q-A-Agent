// Typed client for the FastAPI backend. Shapes mirror src/api/schemas.py.
import { getUserId } from "./storage";

export interface IndexRequest {
  repo_url: string;
  force_reindex?: boolean;
}

export interface IndexResponse {
  repo_url: string;
  reused_existing: boolean;
  num_chunks: number | null;
}

export interface QueryRequest {
  repo_url: string;
  question: string;
  chat_id?: string | null;
}

export interface QueryResponse {
  answer: string;
  sources: string[];
  chat_id: string;
  standalone_question: string | null;
  memory_saved: string | null;
}

export interface ChatSummary {
  id: string;
  repo_url: string;
  title: string;
  updated_at: number;
}

export interface ServerMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: string[];
  standalone_question: string | null;
  created_at: number;
}

export interface ChatDetail extends ChatSummary {
  messages: ServerMessage[];
}

export interface Memory {
  id: string;
  content: string;
  source: "explicit" | "auto";
  created_at: number;
}

export type ErrorCode = "repo_not_indexed" | "chat_not_found" | "not_configured";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code: ErrorCode | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") || "/api";

// FastAPI returns {detail: string} for HTTPException and {detail: [{msg, ...}]} for validation errors.
function extractDetail(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => (d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d))).join("; ");
    }
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-User-Id": getUserId(), ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Could not reach the backend. Is the API server running?");
  }

  if (res.status === 204) return undefined as T;
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const code = res.headers.get("X-Error-Code") as ErrorCode | null;
    throw new ApiError(res.status, extractDetail(body, `Request failed with status ${res.status}`), code);
  }
  return body as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

export const api = {
  health: () => request<{ status: string }>("/health"),
  index: (req: IndexRequest) => request<IndexResponse>("/index", json("POST", req)),
  query: (req: QueryRequest) => request<QueryResponse>("/query", json("POST", req)),

  listChats: (repoUrl: string) => request<ChatSummary[]>(`/chats?repo_url=${encodeURIComponent(repoUrl)}`),
  getChat: (id: string) => request<ChatDetail>(`/chats/${encodeURIComponent(id)}`),
  deleteChat: (id: string) => request<void>(`/chats/${encodeURIComponent(id)}`, { method: "DELETE" }),

  listMemories: () => request<Memory[]>("/memories"),
  addMemory: (content: string) => request<Memory>("/memories", json("POST", { content })),
  deleteMemory: (id: string) => request<void>(`/memories/${encodeURIComponent(id)}`, { method: "DELETE" }),
  clearMemories: () => request<void>("/memories", { method: "DELETE" }),
};
