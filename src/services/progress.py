"""Progress reporting for indexing runs. The indexer reports through this interface;
the job registry turns it into live status for the UI, the CLI ignores it."""

from typing import Any, Protocol

# Ordered steps of an indexing run, with UI labels.
INDEX_STEPS: tuple[tuple[str, str], ...] = (
    ("clone", "Clone repository"),
    ("scan", "Scan files"),
    ("chunk", "Split into chunks"),
    ("embed", "Embed chunks"),
    ("overview", "Write overview"),
)


class IndexProgress(Protocol):
    def step(self, key: str) -> None:
        """Finish the current step and start `key`."""

    def detail(self, text: str) -> None:
        """Short live status for the current step, e.g. "Receiving objects 48%"."""

    def fraction(self, value: float) -> None:
        """How far through the current step we are, 0..1."""

    def stats(self, **values: Any) -> None:
        """Update counters such as files, chunks, embedded, languages."""

    def log(self, message: str) -> None:
        """Append a line to the activity log."""

    def check_cancelled(self) -> None:
        """Raise IndexCancelled if the user asked to stop."""


class NullProgress:
    def step(self, key: str) -> None:
        pass

    def detail(self, text: str) -> None:
        pass

    def fraction(self, value: float) -> None:
        pass

    def stats(self, **values: Any) -> None:
        pass

    def log(self, message: str) -> None:
        pass

    def check_cancelled(self) -> None:
        pass
