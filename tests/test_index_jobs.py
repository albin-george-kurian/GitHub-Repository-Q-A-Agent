import threading
import time

import pytest
from fastapi.testclient import TestClient
from git import GitCommandError

from src.api.main import app
from src.services import index_jobs, qa_service
from src.vectorstore.faiss_store import index_exists

REPO = "https://github.com/acme/gadgets"
FILES = {
    "README.md": "# Gadgets\nA toolkit.\n",
    "src/app.py": "def main():\n    return 1\n" * 20,
    "src/util.py": "def helper(x):\n    return x * 2\n" * 10,
    "docs/guide.md": "## Guide\nUse gadgets wisely.\n",
    "config.json": '{"name": "gadgets"}',
}


@pytest.fixture
def fake_clone(llm, monkeypatch, tmp_path):
    """Replace git clone with a local fixture; `gate` lets a test pause the run right after cloning."""
    gate = threading.Event()
    gate.set()

    def clone(repo_url, on_progress=None):
        root = tmp_path / f"clone-{time.monotonic_ns()}"
        for rel, content in FILES.items():
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        if on_progress:
            on_progress("Receiving objects", 0.5)
            on_progress("Receiving objects", 1.0)
        assert gate.wait(10)
        return str(root)

    monkeypatch.setattr(qa_service, "clone_repo", clone)
    return gate


def wait_for(job_id: str, timeout: float = 15) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = index_jobs.snapshot(index_jobs.get(job_id))
        if snap["status"] != "running":
            return snap
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def test_job_runs_all_steps_and_reports_stats(fake_clone):
    snap = wait_for(index_jobs.start(REPO, force=True).id)

    assert snap["status"] == "done", snap["error"]
    assert [s["status"] for s in snap["steps"]] == ["done"] * 5
    assert snap["progress"] == 1.0
    assert snap["stats"]["files"] == 5
    assert snap["stats"]["folders"] == 2
    assert snap["stats"]["chunks"] == snap["num_chunks"] > 0
    assert snap["stats"]["embedded"] == snap["num_chunks"]
    assert snap["stats"]["languages"][0]["name"] == "Python"
    assert {lang["name"] for lang in snap["stats"]["languages"]} == {"Python", "Markdown", "JSON"}
    messages = [line["message"] for line in snap["log"]]
    assert messages[0].startswith("Cloning") and messages[-1] == "Ready"
    assert index_exists(REPO)


def test_starting_twice_joins_the_running_job(fake_clone):
    fake_clone.clear()
    first = index_jobs.start(REPO, force=True)
    second = index_jobs.start(REPO.upper().replace("HTTPS://GITHUB.COM", "https://github.com"), force=True)
    assert second.id == first.id
    fake_clone.set()
    assert wait_for(first.id)["status"] == "done"


def test_cancel_stops_before_anything_is_written(fake_clone):
    fake_clone.clear()  # hold the run right after cloning
    job = index_jobs.start(REPO, force=True)
    index_jobs.cancel(job.id)
    fake_clone.set()

    snap = wait_for(job.id)
    assert snap["status"] == "cancelled"
    assert [s["status"] for s in snap["steps"]][:2] == ["cancelled", "pending"]
    assert not index_exists(REPO)


def test_cancel_during_embedding(fake_clone, monkeypatch):
    holder: dict = {}
    real_embed = qa_service.embed_chunks

    def embed_then_cancel(chunks, embeddings, on_progress=None, batch_size=32):
        index_jobs.cancel(holder["id"])
        return real_embed(chunks, embeddings, on_progress=on_progress, batch_size=1)

    monkeypatch.setattr(qa_service, "embed_chunks", embed_then_cancel)
    fake_clone.clear()
    holder["id"] = index_jobs.start(REPO, force=True).id
    fake_clone.set()

    snap = wait_for(holder["id"])
    assert snap["status"] == "cancelled"
    assert next(s for s in snap["steps"] if s["key"] == "embed")["status"] == "cancelled"
    assert not index_exists(REPO)


def test_clone_failure_is_reported(llm, monkeypatch):
    def failing_clone(repo_url, on_progress=None):
        raise GitCommandError("clone", 128)

    monkeypatch.setattr(qa_service, "clone_repo", failing_clone)
    snap = wait_for(index_jobs.start(REPO, force=True).id)
    assert snap["status"] == "error"
    assert "Failed to clone repository" in snap["error"]
    assert snap["steps"][0]["status"] == "error"


def test_api_starts_and_polls_jobs(fake_clone):
    client = TestClient(app)
    res = client.post("/index", json={"repo_url": REPO, "force_reindex": True})
    assert res.status_code == 202
    job_id = res.json()["id"]

    wait_for(job_id)
    polled = client.get(f"/index/jobs/{job_id}").json()
    assert polled["status"] == "done"
    assert polled["stats"]["files"] == 5

    assert client.get("/index/jobs/nope").status_code == 404
    assert client.post("/index", json={"repo_url": "https://gitlab.com/a/b"}).status_code == 400


def test_clone_progress_parser_reports_labels():
    from git import RemoteProgress

    from src.ingestion.repo_loader import _CloneProgress

    seen = []
    progress = _CloneProgress(lambda label, frac: seen.append((label, frac)))
    progress.update(RemoteProgress.RECEIVING | RemoteProgress.BEGIN, 5, 10)
    progress.update(RemoteProgress.CHECKING_OUT, 3, None)
    assert seen == [("Receiving objects", 0.5), ("Checking out files", None)]


@pytest.fixture(autouse=True)
def _clear_jobs():
    yield
    for job in list(index_jobs._jobs.values()):
        job.cancel_event.set()
    index_jobs._jobs.clear()
