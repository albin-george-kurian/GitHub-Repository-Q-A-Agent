from collections.abc import Callable
from typing import Any

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import DeterministicFakeEmbedding
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from src.config import settings
from src.memory import llm_tasks
from src.rag import overview, qa_chain
from src.services import chat_service, qa_service
from src.vectorstore.faiss_store import build_and_save_index

REPO = "https://github.com/acme/widgets"


class ScriptedLLM(BaseChatModel):
    """Fake chat model: answers by task (detected from the system prompt) and records every call."""

    responder: Callable[[list[BaseMessage]], str]
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        self.calls.append(list(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(self.responder(messages)))])

    def calls_for(self, task: str) -> list[list[BaseMessage]]:
        return [c for c in self.calls if task in c[0].content]


def default_responder(messages: list[BaseMessage]) -> str:
    system = messages[0].content
    if "Rewrite the user's latest message" in system:
        return "Where is the Signer.verify method tested?"
    if "running summary" in system:
        return "SUMMARY: user explored signing."
    if "Extract durable facts" in system:
        return '["Is new to Python"]'
    if "concise orientation" in system:
        return "Widgets is a signing library."
    return "ANSWER"


TASK_ANSWER = "Retrieved code context"
TASK_REWRITE = "Rewrite the user's latest message"
TASK_SUMMARY = "running summary"
TASK_EXTRACT = "Extract durable facts"


@pytest.fixture
def llm(monkeypatch, tmp_path) -> ScriptedLLM:
    fake = ScriptedLLM(responder=default_responder)
    embeddings = DeterministicFakeEmbedding(size=32)

    for module in (qa_chain, overview, chat_service):
        monkeypatch.setattr(module, "get_llm", lambda: fake)
    monkeypatch.setattr(llm_tasks, "get_fast_llm", lambda: fake)
    for module in (chat_service, qa_service):
        monkeypatch.setattr(module, "get_embeddings", lambda: embeddings)

    monkeypatch.setattr(settings, "memory_db_path", str(tmp_path / "memory.db"))
    monkeypatch.setattr(settings, "index_store_dir", str(tmp_path / "indexes"))
    monkeypatch.setattr(settings, "openai_api_key", None)

    docs = [
        Document(page_content="class Signer:\n    def verify(self, value): ...", metadata={"source": "src/signer.py"}),
        Document(page_content="def test_verify():\n    assert Signer().verify(b'x')", metadata={"source": "tests/test_signer.py"}),
        Document(page_content="# Widgets\nA signing library.", metadata={"source": "README.md"}),
    ]
    build_and_save_index(REPO, docs, embeddings, overview="## Summary\nWidgets is a signing library.")
    return fake
