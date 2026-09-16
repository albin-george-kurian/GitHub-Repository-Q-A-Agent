import hashlib
import os

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src.config import settings


def get_index_path(repo_url: str) -> str:
    """Deterministic on-disk path for a repo's persisted FAISS index."""
    repo_hash = hashlib.sha256(repo_url.encode("utf-8")).hexdigest()[:16]
    return os.path.join(settings.index_store_dir, repo_hash)


def index_exists(repo_url: str) -> bool:
    return os.path.isdir(get_index_path(repo_url))


def build_and_save_index(repo_url: str, chunks: list[Document], embeddings: Embeddings) -> FAISS:
    vector_store = FAISS.from_documents(chunks, embeddings)
    index_path = get_index_path(repo_url)
    os.makedirs(index_path, exist_ok=True)
    vector_store.save_local(index_path)
    return vector_store


def load_index(repo_url: str, embeddings: Embeddings) -> FAISS:
    index_path = get_index_path(repo_url)
    return FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
