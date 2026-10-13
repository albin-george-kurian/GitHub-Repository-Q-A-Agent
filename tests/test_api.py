import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from tests.conftest import REPO

HEADERS = {"X-User-Id": "browser-1234"}


@pytest.fixture
def client(llm):
    return TestClient(app)


def test_user_id_header_is_required(client):
    res = client.post("/query", json={"repo_url": REPO, "question": "hi"})
    assert res.status_code == 400


def test_chat_lifecycle(client):
    first = client.post("/query", headers=HEADERS, json={"repo_url": REPO, "question": "How does signing work?"})
    assert first.status_code == 200
    chat_id = first.json()["chat_id"]

    follow = client.post(
        "/query", headers=HEADERS, json={"repo_url": REPO, "question": "Where is it tested?", "chat_id": chat_id}
    )
    assert follow.json()["chat_id"] == chat_id
    assert follow.json()["standalone_question"] == "Where is the Signer.verify method tested?"

    chats = client.get("/chats", headers=HEADERS, params={"repo_url": REPO + ".git"}).json()
    assert [c["id"] for c in chats] == [chat_id]

    detail = client.get(f"/chats/{chat_id}", headers=HEADERS).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]

    assert client.get(f"/chats/{chat_id}", headers={"X-User-Id": "intruder-99"}).status_code == 404
    assert client.delete(f"/chats/{chat_id}", headers=HEADERS).status_code == 204
    assert client.get("/chats", headers=HEADERS).json() == []


def test_not_found_errors_carry_codes(client):
    not_indexed = client.post(
        "/query", headers=HEADERS, json={"repo_url": "https://github.com/acme/nope", "question": "hi"}
    )
    assert not_indexed.status_code == 404
    assert not_indexed.headers["X-Error-Code"] == "repo_not_indexed"

    missing_chat = client.post(
        "/query", headers=HEADERS, json={"repo_url": REPO, "question": "hi", "chat_id": "nope"}
    )
    assert missing_chat.status_code == 404
    assert missing_chat.headers["X-Error-Code"] == "chat_not_found"


def test_memories_crud_and_remember_command(client):
    res = client.post("/query", headers=HEADERS, json={"repo_url": REPO, "question": "remember that I use VS Code"})
    assert res.json()["memory_saved"] == "I use VS Code"

    created = client.post("/memories", headers=HEADERS, json={"content": "Prefers diagrams"})
    assert created.status_code == 201
    assert client.post("/memories", headers=HEADERS, json={"content": "prefers diagrams."}).status_code == 409

    memories = client.get("/memories", headers=HEADERS).json()
    assert [m["content"] for m in memories] == ["I use VS Code", "Prefers diagrams"]

    assert client.delete(f"/memories/{created.json()['id']}", headers=HEADERS).status_code == 204
    assert client.delete("/memories", headers=HEADERS).status_code == 204
    assert client.get("/memories", headers=HEADERS).json() == []


def test_background_task_learns_preferences(client):
    client.post("/query", headers=HEADERS, json={"repo_url": REPO, "question": "I'm new to Python. What is Signer?"})
    assert [m["content"] for m in client.get("/memories", headers=HEADERS).json()] == ["Is new to Python"]
