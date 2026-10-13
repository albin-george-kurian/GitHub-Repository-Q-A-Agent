"""Indexing runs as background jobs, so the UI can show live progress and cancel them.

Jobs live in memory: they're lost on restart, which is fine because the result
(the saved index) is on disk and an interrupted run never leaves a partial index."""

import logging
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from src.ingestion.repo_url import normalize_repo_url
from src.services.exceptions import (
    IndexBusyError,
    IndexCancelled,
    RepoIndexingError,
    rejected_key_message,
)
from src.services.progress import INDEX_STEPS
from src.services.qa_service import index_repository

logger = logging.getLogger(__name__)

MAX_RUNNING_JOBS = 2  # embedding is memory-hungry; more than this at once risks the whole server
_FINISHED_TTL_SECONDS = 3600
_LOG_LINES = 60
# Share of the overall progress bar each step accounts for.
_STEP_WEIGHTS = {"clone": 0.15, "scan": 0.05, "chunk": 0.05, "embed": 0.65, "overview": 0.10}


@dataclass
class _Step:
    key: str
    label: str
    status: str = "pending"  # pending | active | done | error | cancelled
    detail: str | None = None
    fraction: float = 0.0
    started_at: float | None = None
    finished_at: float | None = None


@dataclass
class IndexJob:
    id: str
    repo_url: str
    force: bool
    started_at: float = field(default_factory=time.time)
    status: str = "running"  # running | done | error | cancelled
    steps: list[_Step] = field(default_factory=lambda: [_Step(k, label) for k, label in INDEX_STEPS])
    stats: dict[str, Any] = field(
        default_factory=lambda: {"files": 0, "folders": 0, "bytes": 0, "chunks": 0, "embedded": 0, "languages": []}
    )
    log: deque = field(default_factory=lambda: deque(maxlen=_LOG_LINES))
    num_chunks: int | None = None
    reused_existing: bool = False
    error: str | None = None
    finished_at: float | None = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


_jobs: dict[str, IndexJob] = {}
_lock = threading.Lock()


class _JobReporter:
    """IndexProgress implementation that records into an IndexJob (thread-safe via the registry lock)."""

    def __init__(self, job: IndexJob):
        self._job = job

    def _active(self) -> _Step | None:
        return next((s for s in self._job.steps if s.status == "active"), None)

    def step(self, key: str) -> None:
        now = time.time()
        with _lock:
            for s in self._job.steps:
                if s.status == "active":
                    s.status, s.finished_at, s.fraction, s.detail = "done", now, 1.0, None
                if s.key == key:
                    s.status, s.started_at = "active", now

    def detail(self, text: str) -> None:
        with _lock:
            if step := self._active():
                step.detail = text

    def fraction(self, value: float) -> None:
        with _lock:
            if step := self._active():
                step.fraction = max(0.0, min(1.0, value))

    def stats(self, **values: Any) -> None:
        with _lock:
            self._job.stats.update(values)

    def log(self, message: str) -> None:
        with _lock:
            self._job.log.append({"t": round(time.time() - self._job.started_at, 1), "message": message})

    def check_cancelled(self) -> None:
        if self._job.cancel_event.is_set():
            raise IndexCancelled()


def _finish(job: IndexJob, status: str, error: str | None = None) -> None:
    now = time.time()
    with _lock:
        job.status, job.error, job.finished_at = status, error, now
        for s in job.steps:
            if s.status == "active":
                s.status = "done" if status == "done" else ("cancelled" if status == "cancelled" else "error")
                s.finished_at = now
            elif status == "done" and s.status == "pending":
                s.status = "done"  # e.g. an existing index was reused
        message = {"done": "Ready", "cancelled": "Cancelled", "error": f"Failed: {error}"}[status]
        job.log.append({"t": round(now - job.started_at, 1), "message": message})


def _run(job: IndexJob) -> None:
    reporter = _JobReporter(job)
    try:
        result = index_repository(job.repo_url, job.force, progress=reporter)
    except IndexCancelled:
        _finish(job, "cancelled")
    except RepoIndexingError as exc:
        _finish(job, "error", str(exc))
    except Exception as exc:
        logger.exception("Indexing failed for %s", job.repo_url)
        _finish(job, "error", rejected_key_message(exc) or f"Indexing failed: {exc}")
    else:
        with _lock:
            job.num_chunks, job.reused_existing = result.num_chunks, result.reused_existing
        _finish(job, "done")


def _prune(now: float) -> None:
    for job_id in [j.id for j in _jobs.values() if j.finished_at and now - j.finished_at > _FINISHED_TTL_SECONDS]:
        del _jobs[job_id]


def start(repo_url: str, force: bool) -> IndexJob:
    """Start indexing in the background, or return the job already indexing this repo.
    Raises InvalidRepoUrlError for bad URLs and IndexBusyError when at capacity."""
    repo_url = normalize_repo_url(repo_url)
    with _lock:
        _prune(time.time())
        running = [j for j in _jobs.values() if j.status == "running"]
        for job in running:
            if job.repo_url == repo_url:
                return job
        if len(running) >= MAX_RUNNING_JOBS:
            raise IndexBusyError("Other repositories are being indexed right now. Try again in a minute.")
        job = IndexJob(id=uuid.uuid4().hex, repo_url=repo_url, force=force)
        _jobs[job.id] = job
    threading.Thread(target=_run, args=(job,), name=f"index-{job.id[:8]}", daemon=True).start()
    return job


def get(job_id: str) -> IndexJob | None:
    with _lock:
        return _jobs.get(job_id)


def cancel(job_id: str) -> IndexJob | None:
    """Request cancellation; it takes effect at the next step or embedding batch."""
    job = get(job_id)
    if job and job.status == "running":
        job.cancel_event.set()
        with _lock:
            job.log.append({"t": round(time.time() - job.started_at, 1), "message": "Cancelling…"})
    return job


def snapshot(job: IndexJob) -> dict[str, Any]:
    """JSON-safe view of a job for the API."""
    with _lock:
        now = time.time()
        progress = 1.0 if job.status == "done" else 0.0
        if job.status != "done":
            for s in job.steps:
                weight = _STEP_WEIGHTS[s.key]
                # Stopped steps keep their partial progress, so a cancelled run shows how far it got.
                progress += weight if s.status == "done" else weight * s.fraction
        return {
            "id": job.id,
            "repo_url": job.repo_url,
            "status": job.status,
            "progress": round(min(progress, 1.0), 4),
            "elapsed": round((job.finished_at or now) - job.started_at, 1),
            "steps": [
                {
                    "key": s.key,
                    "label": s.label,
                    "status": s.status,
                    "detail": s.detail,
                    "duration": round((s.finished_at or now) - s.started_at, 1) if s.started_at else None,
                }
                for s in job.steps
            ],
            "stats": {**job.stats, "languages": list(job.stats["languages"])},
            "log": list(job.log),
            "num_chunks": job.num_chunks,
            "reused_existing": job.reused_existing,
            "error": job.error,
        }

