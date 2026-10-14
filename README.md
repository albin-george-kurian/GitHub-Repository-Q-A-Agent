# GitHub Repository Q&A Agent

A Retrieval-Augmented Generation (RAG) assistant that indexes a public GitHub
repository and answers questions about its code and architecture, grounded
strictly in the repository's own content.

## How it works

1. Shallow-clones the target GitHub repo to a temp directory.
2. Filters and loads source/doc files into LangChain documents.
3. Splits them with a language-aware splitter per file type.
4. Embeds the chunks (OpenAI if `OPENAI_API_KEY` is set, otherwise a local
   HuggingFace model) and stores them in a persisted FAISS index.
5. Retrieves relevant chunks for a question and answers it with a Groq LLM,
   explicitly refusing to guess when the context doesn't contain the answer.

## Memory

Answers draw on several layers of memory, modelled on how assistants like Claude keep context:

| Layer | What it does | Stored in |
| --- | --- | --- |
| Recent turns | Follow-ups like "where is *that* tested?" are rewritten into a standalone question before searching, and recent turns are sent with the prompt | `data/memory.db` |
| Running summary | Once a chat grows past `SUMMARIZE_AFTER_MESSAGES`, older turns are folded into a summary (in the background) | `data/memory.db` |
| Saved chats | Every chat is persisted; reopen it from the sidebar and keep going | `data/memory.db` |
| Repo overview | Generated once at index time (purpose, stack, layout) and included in every prompt, so big-picture questions work | `data/indexes/<id>/overview.md` |
| User memory | Say "remember that …", add items in the Memory panel, or let it learn from what you mention about yourself | `data/memory.db` |
| Past answers | Relevant Q&A from your other chats about the same repo is recalled as a hint | `data/memory.db` |

There are no accounts yet: each browser gets an anonymous ID (sent as `X-User-Id`) that scopes its chats and
memories. It separates users but is not authentication.

## Setup

```bash
python -m venv venv
./venv/Scripts/activate   # Windows
pip install -r requirements.txt
cp .env.example .env      # then fill in GROQ_API_KEY (required)
```

## Usage

### Web app

Run the API and the frontend in two terminals, both from the project root:

```bash
# 1. backend (http://127.0.0.1:8000, interactive docs at /docs)
uvicorn src.api.main:app --reload

# 2. frontend (http://localhost:5173)
cd frontend
npm install
npm run dev
```

In dev, the Vite server proxies `/api/*` to the backend, so no extra setup is
needed. For a production build (`npm run build`) served from another origin, set
`VITE_API_BASE_URL` in `frontend/.env` and add that origin to `CORS_ORIGINS`
in the backend `.env`.

### API

| Method | Path                         | Body                                   | Returns                                                                    |
|--------|------------------------------|----------------------------------------|----------------------------------------------------------------------------|
| GET    | `/health`                    | –                                      | `{"status": "ok"}`                                                         |
| POST   | `/index`                     | `{"repo_url", "force_reindex"?}`       | `202` indexing job (starts one, or joins the run already in progress)      |
| GET    | `/index/jobs/{id}`           | –                                      | Job status: steps, progress (0–1), stats, language breakdown, activity log |
| POST   | `/index/jobs/{id}/cancel`    | –                                      | `202` job; stops at the next step or embedding batch                       |
| POST   | `/query`                     | `{"repo_url", "question", "chat_id"?}` | `{"answer", "sources", "chat_id", "standalone_question", "memory_saved"}`  |
| POST   | `/query/stream`              | same as `/query`                       | The answer as it is written, as Server-Sent Events (below)                 |

`/query/stream` sends `start` `{chat_id}`, then `status` `{stage}` (`rewriting` for follow-ups, `searching`),
`sources` `{sources, standalone_question}`, a `delta` `{text}` per piece of the answer, and finally `done` with
the same fields as `/query`. Request errors (repo not indexed, unknown chat, missing key) are returned as normal
HTTP errors before the stream starts; a failure mid-answer arrives as an `error` `{status, detail, code}` event.
Closing the connection stops the model right away, and the text written so far is kept in the chat. The web app
uses this endpoint, with a Stop button while an answer is being written.

Indexing runs in the background (at most two repositories at once) so the UI can show live progress:
clone → scan → chunk → embed → overview. Jobs are kept in memory; a cancelled or failed run never leaves a
partial index behind.

Chat and memory endpoints (all need an `X-User-Id` header): `GET /chats?repo_url=`, `GET /chats/{id}`,
`DELETE /chats/{id}`, `GET /memories`, `POST /memories`, `DELETE /memories/{id}`, `DELETE /memories`.

### MCP server

The agent is also available as an [MCP](https://modelcontextprotocol.io) server (built with FastMCP), so AI
clients such as Claude Code, Claude Desktop or Cursor can call it as tools. Repositories can be passed as a URL
or as `owner/name`.

| Tool | What it does |
| --- | --- |
| `ask_repository` | Answers a question about the code with file citations. Indexes the repo on first use, streaming progress |
| `get_repo_info` | Description, stars, forks, language, topics, license, default branch, last push |
| `search_issues` / `get_issue` | Search issues (text, `label:bug`, state); read one with its comments |
| `list_pull_requests` / `get_pull_request` | Recent PRs (open/closed/merged); one PR with changed files and diffs |
| `get_file_history` | Recent commits that touched a file or folder |
| `list_releases` | Releases with dates and release notes |

All tools except `ask_repository` are read-only calls to the GitHub API. They work without a token (60
requests/hour); set `GITHUB_TOKEN` in `.env` for 5,000/hour. `ask_repository` uses the same `.env` settings
as the web app (Groq key, embeddings).

Connect it to **Claude Code** (use absolute paths; on macOS/Linux the interpreter is `venv/bin/python`):

```bash
claude mcp add repo-qa -- "<repo>/venv/Scripts/python.exe" "<repo>/scripts/mcp_server.py"
```

or to **Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "repo-qa": {
      "command": "<repo>\\venv\\Scripts\\python.exe",
      "args": ["<repo>\\scripts\\mcp_server.py"]
    }
  }
}
```

For remote clients, run it over streamable HTTP instead (served at `http://127.0.0.1:8765/mcp`; keep it on
localhost unless you put authentication in front of it):

```bash
python scripts/mcp_server.py --transport http --port 8765
```

### Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use a scripted fake LLM and fake embeddings, so they need no API keys or network.

### CLI

```bash
python scripts/run_pipeline.py <repo_url> "<question>"

# example
python scripts/run_pipeline.py https://github.com/psf/requests "What HTTP methods does this library support?"

# force a rebuild of the index instead of reusing a cached one
python scripts/run_pipeline.py <repo_url> "<question>" --force-reindex
```

## Status

- **Stage 1 (Foundation/MVP)**: CLI-based end-to-end RAG pipeline.
- **Stage 2 (Backend API)**: FastAPI `/index` and `/query` endpoints.
- **Frontend**: React + TypeScript (Vite) UI in [`frontend/`](frontend/).
- **MCP server**: repository Q&A and GitHub tools for AI clients ([`src/mcp_server/`](src/mcp_server/)).
- **Stage 3**: further improvements, planned.
