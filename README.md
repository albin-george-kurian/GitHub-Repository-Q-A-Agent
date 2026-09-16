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

## Setup

```bash
python -m venv venv
./venv/Scripts/activate   # Windows
pip install -r requirements.txt
cp .env.example .env      # then fill in GROQ_API_KEY (required)
```

## Usage

```bash
python scripts/run_pipeline.py <repo_url> "<question>"

# example
python scripts/run_pipeline.py https://github.com/psf/requests "What HTTP methods does this library support?"

# force a rebuild of the index instead of reusing a cached one
python scripts/run_pipeline.py <repo_url> "<question>" --force-reindex
```

## Status

**Stage 1 (Foundation/MVP)** — CLI-based end-to-end RAG pipeline. A FastAPI
backend (Stage 2) and further improvements (Stage 3) are planned next.
