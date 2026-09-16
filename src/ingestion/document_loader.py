import os

from langchain_core.documents import Document

from src.ingestion.file_filter import iter_included_files


def load_repo_documents(repo_path: str, max_file_size_bytes: int) -> list[Document]:
    """Read filtered files from a cloned repo into LangChain Documents with path metadata."""
    documents: list[Document] = []

    for full_path in iter_included_files(repo_path, max_file_size_bytes):
        try:
            with open(full_path, encoding="utf-8") as f:
                content = f.read()
        except (UnicodeDecodeError, OSError):
            continue

        if not content.strip():
            continue

        relative_path = os.path.relpath(full_path, repo_path).replace(os.sep, "/")
        extension = os.path.splitext(full_path)[1].lower()

        documents.append(
            Document(
                page_content=content,
                metadata={"source": relative_path, "extension": extension},
            )
        )

    return documents
