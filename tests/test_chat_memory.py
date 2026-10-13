import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.config import settings
from src.memory import store
from src.services import chat_service
from src.services.exceptions import ChatNotFoundError, RepoNotIndexedError
from tests.conftest import REPO, TASK_ANSWER, TASK_EXTRACT, TASK_REWRITE, TASK_SUMMARY

USER = "user-0001"


def test_first_turn_creates_chat_without_rewrite(llm):
    turn = chat_service.chat(USER, REPO, "How does signing work?")

    assert turn.answer == "ANSWER"
    assert turn.standalone_question is None
    assert llm.calls_for(TASK_REWRITE) == []
    chat = store.get_chat(USER, turn.chat_id)
    assert chat.title == "How does signing work?"
    assert [m.role for m in store.get_messages(turn.chat_id)] == ["user", "assistant"]
    # Repo overview is part of every answer prompt.
    assert "Widgets is a signing library." in llm.calls_for(TASK_ANSWER)[0][0].content


def test_follow_up_sends_history_and_searches_rewritten_question(llm):
    first = chat_service.chat(USER, REPO, "How does signing work?")
    second = chat_service.chat(USER, REPO, "Where is that tested?", first.chat_id)

    assert second.chat_id == first.chat_id
    assert second.standalone_question == "Where is the Signer.verify method tested?"
    assert len(llm.calls_for(TASK_REWRITE)) == 1

    prompt = llm.calls_for(TASK_ANSWER)[-1]
    assert isinstance(prompt[1], HumanMessage) and prompt[1].content == "How does signing work?"
    assert isinstance(prompt[2], AIMessage) and prompt[2].content == "ANSWER"
    assert prompt[-1].content == "Where is that tested?"

    stored = store.get_messages(first.chat_id)[-1]
    assert stored.standalone_question == "Where is the Signer.verify method tested?"


def test_explicit_remember_is_stored_and_used_in_later_prompts(llm):
    turn = chat_service.chat(USER, REPO, "Remember that I prefer short answers.")

    assert turn.memory_saved == "I prefer short answers"
    assert llm.calls == []  # no LLM needed to remember
    assert [m.content for m in store.list_memories(USER)] == ["I prefer short answers"]

    chat_service.chat(USER, REPO, "What does Signer do?")
    assert "I prefer short answers" in llm.calls_for(TASK_ANSWER)[-1][0].content


def test_question_mentioning_remember_is_not_a_command(llm):
    turn = chat_service.chat(USER, REPO, "Remember how verify handles bad input?")
    assert turn.memory_saved is None
    assert store.list_memories(USER) == []


def test_long_chat_is_compacted_into_summary(llm, monkeypatch):
    monkeypatch.setattr(settings, "summarize_after_messages", 4)
    monkeypatch.setattr(settings, "history_recent_messages", 2)

    chat_id = None
    for q in ["q1", "q2", "q3"]:
        chat_id = chat_service.chat(USER, REPO, q, chat_id).chat_id
    chat_service.after_turn(USER, chat_id, "q3")

    chat = store.get_chat(USER, chat_id)
    assert chat.summary == "SUMMARY: user explored signing."
    remaining = store.get_messages(chat_id, after_id=chat.summarized_upto)
    assert [m.content for m in remaining] == ["q3", "ANSWER"]

    chat_service.chat(USER, REPO, "q4", chat_id)
    prompt = llm.calls_for(TASK_ANSWER)[-1]
    assert "SUMMARY: user explored signing." in prompt[0].content
    assert [m.content for m in prompt[1:]] == ["q3", "ANSWER", "q4"]


def test_preferences_are_learned_only_when_user_talks_about_themselves(llm):
    chat_service.after_turn(USER, "missing-chat", "What does verify return?")
    assert llm.calls_for(TASK_EXTRACT) == []

    chat_service.after_turn(USER, "missing-chat", "I'm new to Python, how does verify work?")
    memories = store.list_memories(USER)
    assert [(m.content, m.source) for m in memories] == [("Is new to Python", "auto")]

    chat_service.after_turn(USER, "missing-chat", "I'm new to Python, really")
    assert len(store.list_memories(USER)) == 1  # duplicates aren't stored twice


def test_related_answers_from_other_chats_are_recalled(llm):
    chat_service.chat(USER, REPO, "How does signing work?")
    chat_service.chat(USER, REPO, "How does signing work?")  # new chat, same question

    prompt = llm.calls_for(TASK_ANSWER)[-1][0].content
    assert "earlier conversations" in prompt
    assert "Q: How does signing work?" in prompt


def test_related_answers_are_scoped_to_the_user(llm):
    chat_service.chat(USER, REPO, "How does signing work?")
    chat_service.chat("someone-else", REPO, "How does signing work?")
    assert "earlier conversations" not in llm.calls_for(TASK_ANSWER)[-1][0].content


def test_chats_are_private_and_bound_to_their_repo(llm):
    turn = chat_service.chat(USER, REPO, "hello")
    with pytest.raises(ChatNotFoundError):
        chat_service.chat("someone-else", REPO, "hi", turn.chat_id)
    assert store.get_chat("someone-else", turn.chat_id) is None


def test_unindexed_repo_is_rejected(llm):
    with pytest.raises(RepoNotIndexedError):
        chat_service.chat(USER, "https://github.com/acme/other", "hello")


def test_memory_cap_drops_oldest_learned_memories_first(llm):
    store.add_memory(USER, "explicit one", "explicit", max_per_user=3)
    store.add_memory(USER, "auto one", "auto", max_per_user=3)
    store.add_memory(USER, "auto two", "auto", max_per_user=3)
    store.add_memory(USER, "auto three", "auto", max_per_user=3)

    assert sorted(m.content for m in store.list_memories(USER)) == ["auto three", "auto two", "explicit one"]
