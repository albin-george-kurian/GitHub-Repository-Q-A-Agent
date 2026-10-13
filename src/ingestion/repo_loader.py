import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Callable

from git import RemoteProgress, Repo

CloneProgressCallback = Callable[[str, float | None], None]


class _CloneProgress(RemoteProgress):
    """Forwards git's clone stages ("Receiving objects 48%") to a simple callback."""

    _LABELS = {
        RemoteProgress.COUNTING: "Counting objects",
        RemoteProgress.COMPRESSING: "Compressing objects",
        RemoteProgress.RECEIVING: "Receiving objects",
        RemoteProgress.RESOLVING: "Resolving deltas",
        RemoteProgress.CHECKING_OUT: "Checking out files",
    }

    def __init__(self, callback: CloneProgressCallback):
        super().__init__()
        self._callback = callback

    def update(self, op_code, cur_count, max_count=None, message="") -> None:
        label = self._LABELS.get(op_code & RemoteProgress.OP_MASK)
        if label is None:
            return
        fraction = float(cur_count) / float(max_count) if max_count else None
        try:
            self._callback(label, fraction)
        except Exception:
            pass  # progress reporting must never break the clone


def clone_repo(repo_url: str, on_progress: CloneProgressCallback | None = None) -> str:
    """Shallow-clone a public GitHub repo into a temp directory and return its local path."""
    local_path = tempfile.mkdtemp(prefix="repo_qa_")
    try:
        # GIT_TERMINAL_PROMPT=0: fail fast on private/missing repos instead of hanging on a credential prompt.
        Repo.clone_from(
            repo_url,
            local_path,
            depth=1,
            env={"GIT_TERMINAL_PROMPT": "0"},
            progress=_CloneProgress(on_progress) if on_progress else None,
        )
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
