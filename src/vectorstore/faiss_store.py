import hashlib
import os
import shutil
import tempfile
from threading import Lock

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src.config import settings

_INDEX_FILE = "index.faiss"

# Loaded indexes, keyed by path, so queries don't re-read the index from disk every time.
_loaded: dict[str, FAISS] = {}
_loaded_lock = Lock()


def get_index_path(repo_url: str) -> str:
    """Deterministic on-disk path for a repo's persisted FAISS index.

    Keyed by the embedding model too: an index built with one model can't be
    queried with another (vector dimensions differ)."""
    key = f"{repo_url}|{settings.embedding_model_id}"
    repo_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return os.path.join(settings.index_store_dir, repo_hash)


def index_exists(repo_url: str) -> bool:
    return os.path.isfile(os.path.join(get_index_path(repo_url), _INDEX_FILE))


def build_and_save_index(repo_url: str, chunks: list[Document], embeddings: Embeddings) -> FAISS:
    vector_store = FAISS.from_documents(chunks, embeddings)
    index_path = get_index_path(repo_url)

    # Write to a temp dir and swap it in, so a failed save never leaves a half-written index behind.
    os.makedirs(settings.index_store_dir, exist_ok=True)
    tmp_path = tempfile.mkdtemp(prefix=".tmp_", dir=settings.index_store_dir)
    try:
        vector_store.save_local(tmp_path)
        shutil.rmtree(index_path, ignore_errors=True)
        os.replace(tmp_path, index_path)
    except Exception:
        shutil.rmtree(tmp_path, ignore_errors=True)
        raise

    with _loaded_lock:
        _loaded[index_path] = vector_store
    return vector_store


def load_index(repo_url: str, embeddings: Embeddings) -> FAISS:
    index_path = get_index_path(repo_url)
    with _loaded_lock:
        if index_path not in _loaded:
            # Indexes are only ever written by this app, so unpickling the docstore is safe here.
            _loaded[index_path] = FAISS.load_local(index_path, embeddings, allow_dangerous_deserialization=True)
        return _loaded[index_path]
