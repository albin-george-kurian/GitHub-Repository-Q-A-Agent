// Typed client for the FastAPI backend. Shapes mirror src/api/schemas.py.
import { getUserId } from "./storage";

export interface IndexRequest {
  repo_url: string;
  force_reindex?: boolean;
}

export type IndexStepKey = "clone" | "scan" | "chunk" | "embed" | "overview";
export type IndexStepStatus = "pending" | "active" | "done" | "error" | "cancelled";

export interface IndexStep {
  key: IndexStepKey;
  label: string;
  status: IndexStepStatus;
  detail: string | null;
  duration: number | null;
}

export interface IndexJob {
  id: string;
  repo_url: string;
  status: "running" | "done" | "error" | "cancelled";
  progress: number;
  elapsed: number;
  steps: IndexStep[];
  stats: {
    files: number;
    folders: number;
    bytes: number;
    chunks: number;
    embedded: number;
    languages: { name: string; bytes: number }[];
  };
  log: { t: number; message: string }[];
  num_chunks: number | null;
  reused_existing: boolean;
  error: string | null;
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

/** Events of POST /query/stream before the final `done` (which carries a QueryResponse). */
export type StreamEvent =
  | { type: "start"; chat_id: string }
  | { type: "status"; stage: "rewriting" | "searching" }
  | { type: "sources"; sources: string[]; standalone_question: string | null }
  | { type: "delta"; text: string };

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

export type ErrorCode = "repo_not_indexed" | "chat_not_found" | "not_configured" | "index_busy" | "job_not_found";

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

const UNREACHABLE = "Could not reach the backend. Is the API server running?";

async function send(path: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-User-Id": getUserId(), ...init?.headers },
    });
  } catch (err) {
    if (init?.signal?.aborted) throw err; // a deliberate stop, not a network problem
    throw new ApiError(0, UNREACHABLE);
  }
}

async function errorFrom(res: Response): Promise<ApiError> {
  const body: unknown = await res.json().catch(() => null);
  const code = res.headers.get("X-Error-Code") as ErrorCode | null;
  return new ApiError(res.status, extractDetail(body, `Request failed with status ${res.status}`), code);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await send(path, init);
  if (res.status === 204) return undefined as T;
  if (!res.ok) throw await errorFrom(res);
  return (await res.json().catch(() => null)) as T;
}

const json = (method: string, body: unknown): RequestInit => ({ method, body: JSON.stringify(body) });

/**
 * Ask a question and stream the answer (Server-Sent Events over a POST, so not EventSource).
 * Calls onEvent as it arrives and resolves with the finished turn. Aborting `signal` stops the
 * answer; the promise then rejects with the AbortError.
 */
async function queryStream(
  req: QueryRequest,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<QueryResponse> {
  const res = await send("/query/stream", { ...json("POST", req), signal });
  if (!res.ok || !res.body) throw await errorFrom(res);

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    let chunk: ReadableStreamReadResult<string>;
    try {
      chunk = await reader.read();
    } catch (err) {
      if (signal?.aborted) throw err;
      throw new ApiError(0, "The connection dropped before the answer finished.");
    }
    if (chunk.done) break;
    buffer += chunk.value;

    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      let name = "message";
      const data: string[] = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) name = line.slice(7);
        else if (line.startsWith("data: ")) data.push(line.slice(6));
        // lines starting with ":" are keep-alive comments
      }
      if (data.length === 0) continue;
      const payload = JSON.parse(data.join("\n"));
      if (name === "done") return payload as QueryResponse;
      if (name === "error") throw new ApiError(payload.status ?? 502, payload.detail, payload.code ?? null);
      onEvent({ type: name, ...payload } as StreamEvent);
    }
  }
  throw new ApiError(0, "The connection closed before the answer finished.");
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  startIndex: (req: IndexRequest) => request<IndexJob>("/index", json("POST", req)),
  getIndexJob: (id: string) => request<IndexJob>(`/index/jobs/${encodeURIComponent(id)}`),
  cancelIndexJob: (id: string) =>
    request<IndexJob>(`/index/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" }),
  query: (req: QueryRequest) => request<QueryResponse>("/query", json("POST", req)),
  queryStream,

  listChats: (repoUrl: string) => request<ChatSummary[]>(`/chats?repo_url=${encodeURIComponent(repoUrl)}`),
  getChat: (id: string) => request<ChatDetail>(`/chats/${encodeURIComponent(id)}`),
  deleteChat: (id: string) => request<void>(`/chats/${encodeURIComponent(id)}`, { method: "DELETE" }),

  listMemories: () => request<Memory[]>("/memories"),
  addMemory: (content: string) => request<Memory>("/memories", json("POST", { content })),
  deleteMemory: (id: string) => request<void>(`/memories/${encodeURIComponent(id)}`, { method: "DELETE" }),
  clearMemories: () => request<void>("/memories", { method: "DELETE" }),
};
