"""Small LLM calls that keep conversational memory working. All run on the fast model."""

import json
import re
from collections.abc import Sequence

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from src.llm.groq_client import get_fast_llm
from src.memory.store import Message

_parser = StrOutputParser()


def _transcript(messages: Sequence[Message], max_chars: int = 1200) -> str:
    lines = []
    for m in messages:
        speaker = "User" if m.role == "user" else "Assistant"
        text = m.content if len(m.content) <= max_chars else m.content[:max_chars] + " …"
        lines.append(f"{speaker}: {text}")
    return "\n\n".join(lines)


def condense_question(question: str, history: Sequence[Message], summary: str) -> str:
    """Rewrite a follow-up ("where is that tested?") into a standalone question for retrieval."""
    context = ""
    if summary:
        context += f"Summary of earlier conversation:\n{summary}\n\n"
    context += f"Recent conversation:\n{_transcript(history, max_chars=600)}"

    messages = [
        SystemMessage(
            "Rewrite the user's latest message as a single standalone question about the code repository, "
            "resolving pronouns and references (it, that, this function, the second one) using the "
            "conversation. Keep names of files, functions and classes exactly. If the message is already "
            "standalone, return it unchanged. Output only the question, nothing else."
        ),
        HumanMessage(f"{context}\n\nLatest message: {question}"),
    ]
    rewritten = _parser.invoke(get_fast_llm().invoke(messages)).strip().strip('"')
    return rewritten or question


def summarize_conversation(previous_summary: str, messages: Sequence[Message]) -> str:
    """Fold older turns into a running summary so long chats stay within the prompt budget."""
    prompt = (
        f"Existing summary:\n{previous_summary or '(none)'}\n\n"
        f"New conversation turns to fold in:\n{_transcript(messages)}"
    )
    result = get_fast_llm().invoke(
        [
            SystemMessage(
                "You maintain a running summary of a conversation about a code repository. Update the "
                "summary with the new turns. Keep: what the user is trying to do, questions asked, key "
                "findings, file/function names mentioned, and any decisions. Drop pleasantries. "
                "Max 200 words, plain prose or short bullets. Output only the summary."
            ),
            HumanMessage(prompt),
        ]
    )
    return _parser.invoke(result).strip()


# Only worth an LLM call when the user talks about themselves or how they want answers.
_SELF_REFERENCE = re.compile(
    r"\b(i|i'm|im|i am|i've|my|me|mine|prefer|always|never|from now on|call me|please (?:use|answer|explain|keep))\b",
    re.IGNORECASE,
)


def might_contain_preferences(text: str) -> bool:
    return bool(_SELF_REFERENCE.search(text))


def extract_memories(user_message: str, existing: Sequence[str]) -> list[str]:
    """Pull durable facts/preferences about the user (not about the code) out of a message."""
    known = "\n".join(f"- {m}" for m in existing) or "(none)"
    result = get_fast_llm().invoke(
        [
            SystemMessage(
                "Extract durable facts or preferences about the USER that would help personalize future "
                "answers: their role, experience level, languages/tools they know, preferred answer style "
                "or length, language to reply in, or long-term goals. Ignore anything that is just a "
                "question about the code, temporary, or already known. Write each item as a short "
                "third-person statement, e.g. \"Prefers concise answers with code examples\". "
                'Respond with only a JSON array of strings, or [] if there is nothing to store.'
            ),
            HumanMessage(f"Already known about the user:\n{known}\n\nUser message:\n{user_message}"),
        ]
    )
    return _parse_string_list(_parser.invoke(result))


def _parse_string_list(raw: str) -> list[str]:
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return []
    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []
    return [s.strip() for s in items if isinstance(s, str) and 3 <= len(s.strip()) <= 300][:5]
