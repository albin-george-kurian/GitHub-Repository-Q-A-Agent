"""Server-Sent Events over a generator that is always closed when the response ends."""

import json
from collections.abc import Generator
from typing import Any

import anyio
from starlette.background import BackgroundTask
from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send


def sse_event(event: str, data: Any) -> bytes:
    # json.dumps escapes newlines, so the payload always fits on a single `data:` line.
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


class EventStream(StreamingResponse):
    """text/event-stream response over a sync generator of encoded events.

    When the client disconnects, Starlette stops iterating but leaves the generator suspended until
    garbage collection, so its cleanup (here: saving a stopped answer) could run much later or never.
    This closes it as soon as the response ends, for whatever reason."""

    media_type = "text/event-stream"

    def __init__(self, content: Generator[bytes], background: BackgroundTask | None = None) -> None:
        # X-Accel-Buffering: stop nginx-style proxies from holding events back.
        super().__init__(content, headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}, background=background)
        self._content = content

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Starlette has waited for any next() still running in a worker thread, so closing is safe.
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(self._content.close)
