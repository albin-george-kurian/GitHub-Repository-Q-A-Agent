"""Streamed answers: the event sequence, stopping mid-answer, and the SSE endpoint."""

import json

import anyio
import pytest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from src.api.main import app
from src.api.streaming import EventStream, sse_event
from src.memory import store
from src.services import chat_service
from src.services.chat_service import ChatTurn, Delta, Retrieved, Status
from src.services.exceptions import RepoNotIndexedError
from tests.conftest import REPO, TASK_ANSWER, ScriptedLLM, default_responder

USER = "user-0001"
HEADERS = {"X-User-Id": "browser-1234"}
ANSWER = "Signer.verify checks the signature in src/signer.py."


@pytest.fixture
def wordy(llm, monkeypatch):
    """The fake LLM answers with several words, so the answer arrives in several pieces."""
    monkeypatch.setattr(
        llm, "responder", lambda messages: ANSWER if TASK_ANSWER in messages[0].content else default_responder(messages)
    )
    return llm


def kinds(events):
    return [type(e).__name__ for e in events]


# ---------- chat_service ----------


def test_first_turn_streams_events_in_order(wordy):
    events = list(chat_service.start_chat(USER, REPO, "How does signing work?"))

    assert kinds(events[:3]) == ["Started", "Status", "Retrieved"]
    assert events[1] == Status("searching")
    deltas = [e for e in events if isinstance(e, Delta)]
    assert len(deltas) > 1
    turn = events[-1]
    assert isinstance(turn, ChatTurn) and turn.answer == "".join(d.text for d in deltas) == ANSWER
    assert turn.chat_id == events[0].chat_id
    assert events[2] == Retrieved(turn.sources, None)
    assert [m.content for m in store.get_messages(turn.chat_id)] == ["How does signing work?", ANSWER]


def test_follow_up_reports_rewriting_before_searching(wordy):
    first = chat_service.chat(USER, REPO, "How does signing work?")
    events = list(chat_service.start_chat(USER, REPO, "Where is that tested?", first.chat_id))

    assert [e.stage for e in events if isinstance(e, Status)] == ["rewriting", "searching"]
    retrieved = next(e for e in events if isinstance(e, Retrieved))
    assert retrieved.standalone_question == "Where is the Signer.verify method tested?"


def test_stopping_mid_answer_keeps_the_partial_text(wordy):
    events = chat_service.start_chat(USER, REPO, "How does signing work?")
    seen = []
    for event in events:
        seen.append(event)
        if kinds(seen).count("Delta") == 2:
            break
    events.close()

    partial = "".join(e.text for e in seen if isinstance(e, Delta))
    assert partial and partial != ANSWER
    chat_id = seen[0].chat_id
    assert [m.content for m in store.get_messages(chat_id)] == ["How does signing work?", partial]
    assert [c.id for c in store.list_chats(USER, REPO)] == [chat_id]


def test_stopping_stops_the_model(wordy, monkeypatch):
    pulled = []
    stream = ScriptedLLM._stream

    def counting(self, *args, **kwargs):
        for chunk in stream(self, *args, **kwargs):
            pulled.append(chunk)
            yield chunk

    monkeypatch.setattr(ScriptedLLM, "_stream", counting)
    events = chat_service.start_chat(USER, REPO, "How does signing work?")
    next(e for e in events if isinstance(e, Delta))
    events.close()

    # Nothing kept reading the model's output after the stop (a LangChain `llm | parser` chain would).
    assert len(pulled) == 2  # the empty "reasoning" chunk and the first word


def test_stopping_before_the_answer_saves_nothing(wordy):
    events = chat_service.start_chat(USER, REPO, "How does signing work?")
    started = next(events)
    events.close()

    assert store.get_messages(started.chat_id) == []
    assert store.list_chats(USER, REPO) == []  # the empty chat stays hidden…

    chat_service.chat(USER, REPO, "What is Signer?", started.chat_id)  # …until the next question lands in it
    assert [c.id for c in store.list_chats(USER, REPO)] == [started.chat_id]


def test_request_errors_are_raised_before_streaming(llm):
    with pytest.raises(RepoNotIndexedError):
        chat_service.start_chat(USER, "https://github.com/acme/other", "hello")  # no next() needed


def test_remember_is_a_single_done_event(llm):
    events = list(chat_service.start_chat(USER, REPO, "remember that I use VS Code"))
    assert kinds(events) == ["ChatTurn"] and events[0].memory_saved == "I use VS Code"


# ---------- POST /query/stream ----------


@pytest.fixture
def client(wordy):
    return TestClient(app)


def read_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if not line.startswith(":"))
        events.append((fields["event"], json.loads(fields["data"])))
    return events


def test_stream_endpoint(client):
    res = client.post("/query/stream", headers=HEADERS, json={"repo_url": REPO, "question": "I'm new to Python. How does signing work?"})
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/event-stream")

    events = read_sse(res.text)
    names = [name for name, _ in events]
    assert names[:3] == ["start", "status", "sources"] and names[-1] == "done"
    assert "".join(data["text"] for name, data in events if name == "delta") == ANSWER

    done = events[-1][1]
    assert done == {
        "chat_id": events[0][1]["chat_id"],
        "answer": ANSWER,
        "sources": events[2][1]["sources"],
        "standalone_question": None,
        "memory_saved": None,
    }
    detail = client.get(f"/chats/{done['chat_id']}", headers=HEADERS).json()
    assert [m["content"] for m in detail["messages"]][-1] == ANSWER
    # Housekeeping still runs after the stream: the preference was learned.
    assert [m["content"] for m in client.get("/memories", headers=HEADERS).json()] == ["Is new to Python"]


def test_stream_request_errors_keep_http_status(client):
    not_indexed = client.post("/query/stream", headers=HEADERS, json={"repo_url": "https://github.com/acme/nope", "question": "hi"})
    assert not_indexed.status_code == 404 and not_indexed.headers["X-Error-Code"] == "repo_not_indexed"

    missing_chat = client.post("/query/stream", headers=HEADERS, json={"repo_url": REPO, "question": "hi", "chat_id": "nope"})
    assert missing_chat.status_code == 404 and missing_chat.headers["X-Error-Code"] == "chat_not_found"


def test_failure_mid_stream_becomes_an_error_event(client, monkeypatch):
    def failing(*args, **kwargs):
        yield "Partial "
        raise RuntimeError("connection reset")

    monkeypatch.setattr(chat_service, "stream_answer", failing)
    res = client.post("/query/stream", headers=HEADERS, json={"repo_url": REPO, "question": "I'm new to Python. What is Signer?"})

    events = read_sse(res.text)
    assert [name for name, _ in events] == ["start", "status", "sources", "delta", "error"]
    assert events[-1][1] == {"status": 502, "detail": "LLM or embedding provider error: connection reset", "code": None}
    assert client.get("/chats", headers=HEADERS).json() == []  # a failed answer isn't saved
    assert client.get("/memories", headers=HEADERS).json() == []  # and no housekeeping ran


# ---------- EventStream: a client that hangs up closes the generator immediately ----------


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])  # 2.3: disconnect message (uvicorn); 2.4: send() raises
async def test_event_stream_closes_generator_when_client_disconnects(spec_version):
    closed = []

    def events():
        try:
            for i in range(10_000):
                yield sse_event("delta", {"text": str(i)})
        except GeneratorExit:
            closed.append(True)
            raise

    sent = []
    gone = anyio.Event()

    async def send(message):
        if gone.is_set() and spec_version == "2.4":
            raise OSError("connection lost")
        sent.append(message)
        if len(sent) == 4:
            gone.set()

    async def receive():
        await gone.wait()
        return {"type": "http.disconnect"}

    scope = {"type": "http", "asgi": {"spec_version": spec_version}}
    try:
        await EventStream(events())(scope, receive, send)
    except ClientDisconnect:
        assert spec_version == "2.4"

    assert closed == [True]  # closed right away, not left for garbage collection
    assert len(sent) < 100
    assert sent[0]["headers"] and (b"content-type", b"text/event-stream; charset=utf-8") in sent[0]["headers"]
