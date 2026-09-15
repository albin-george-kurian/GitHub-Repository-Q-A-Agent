import os

from langchain_text_splitters import Language

EXCLUDED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".idea", ".vscode", "target", "vendor", ".next", ".pytest_cache", "coverage",
}

EXCLUDED_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock",
}

# Extension -> LangChain Language enum, used to pick a code-aware splitter.
LANGUAGE_BY_EXTENSION: dict[str, Language] = {
    ".py": Language.PYTHON,
    ".js": Language.JS,
    ".jsx": Language.JS,
    ".ts": Language.TS,
    ".tsx": Language.TS,
    ".java": Language.JAVA,
    ".go": Language.GO,
    ".rs": Language.RUST,
    ".rb": Language.RUBY,
    ".php": Language.PHP,
    ".cpp": Language.CPP,
    ".c": Language.CPP,
    ".h": Language.CPP,
    ".hpp": Language.CPP,
    ".cs": Language.CSHARP,
    ".kt": Language.KOTLIN,
    ".swift": Language.SWIFT,
    ".scala": Language.SCALA,
}

# Non-code files worth indexing (docs/config), split generically instead of as code.
DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini"}

INCLUDED_EXTENSIONS = set(LANGUAGE_BY_EXTENSION) | DOC_EXTENSIONS


def iter_included_files(repo_path: str, max_file_size_bytes: int):
    """Walk repo_path and yield absolute paths of files worth ingesting."""
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]

        for filename in files:
            if filename in EXCLUDED_FILENAMES:
                continue

            ext = os.path.splitext(filename)[1].lower()
            if ext not in INCLUDED_EXTENSIONS:
                continue

            full_path = os.path.join(root, filename)
            try:
                if os.path.getsize(full_path) > max_file_size_bytes:
                    continue
            except OSError:
                continue

            yield full_path
