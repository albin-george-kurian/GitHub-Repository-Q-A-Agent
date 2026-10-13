// Typed client for the FastAPI backend. Shapes mirror src/api/schemas.py.

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
}

export interface QueryResponse {
  answer: string;
  sources: string[];
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
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
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Could not reach the backend. Is the API server running?");
  }

  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(res.status, extractDetail(body, `Request failed with status ${res.status}`));
  }
  return body as T;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  index: (req: IndexRequest) => request<IndexResponse>("/index", { method: "POST", body: JSON.stringify(req) }),
  query: (req: QueryRequest) => request<QueryResponse>("/query", { method: "POST", body: JSON.stringify(req) }),
};
