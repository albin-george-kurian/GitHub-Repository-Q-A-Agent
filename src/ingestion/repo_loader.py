import os
import shutil
import stat
import sys
import tempfile

from git import Repo


def clone_repo(repo_url: str) -> str:
    """Shallow-clone a public GitHub repo into a temp directory and return its local path."""
    local_path = tempfile.mkdtemp(prefix="repo_qa_")
    try:
        # GIT_TERMINAL_PROMPT=0: fail fast on private/missing repos instead of hanging on a credential prompt.
        Repo.clone_from(repo_url, local_path, depth=1, env={"GIT_TERMINAL_PROMPT": "0"})
    except Exception:
        cleanup_repo(local_path)
        raise
    return local_path


def _make_writable_and_retry(func, path, _exc) -> None:
    # Git marks object/pack files read-only, which makes rmtree fail on Windows.
    os.chmod(path, stat.S_IWRITE)
    func(path)


def cleanup_repo(local_path: str) -> None:
    """Remove a previously cloned repo's temp directory. Best-effort: never raises,
    since it runs in `finally` blocks and must not mask the original error."""
    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(local_path, onexc=_make_writable_and_retry)
        else:
            shutil.rmtree(local_path, onerror=_make_writable_and_retry)
    except OSError:
        pass
