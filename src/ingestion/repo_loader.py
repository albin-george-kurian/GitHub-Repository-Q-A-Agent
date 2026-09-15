import shutil
import tempfile

from git import Repo


def clone_repo(repo_url: str) -> str:
    """Shallow-clone a public GitHub repo into a temp directory and return its local path."""
    local_path = tempfile.mkdtemp(prefix="repo_qa_")
    Repo.clone_from(repo_url, local_path, depth=1)
    return local_path


def cleanup_repo(local_path: str) -> None:
    """Remove a previously cloned repo's temp directory."""
    shutil.rmtree(local_path, ignore_errors=True)
