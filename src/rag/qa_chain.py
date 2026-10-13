from collections.abc import Sequence

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from src.llm.groq_client import get_llm
from src.memory.store import Message, RelatedQA

RULES = (
    "You are an assistant that answers questions about a specific GitHub repository. Ground every "
    "claim about the code in the retrieved code context or the repository overview. Do not invent "
    "files, functions, or functionality that isn't shown there. If they don't contain enough "
    "information, say the information could not be found in the indexed repository instead of "
    "guessing. Use the conversation so far to understand follow-up questions. Earlier answers from "
    "past conversations are hints only; prefer the code context when they disagree."
)


def format_docs(docs: Sequence[Document]) -> str:
    return "\n\n".join(f"[{doc.metadata.get('source', 'unknown')}]\n{doc.page_content}" for doc in docs)


def sources_of(docs: Sequence[Document]) -> list[str]:
    return sorted({doc.metadata.get("source", "unknown") for doc in docs})


def _clip(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[:max_chars] + " …"


def build_messages(
    question: str,
    docs: Sequence[Document],
    *,
    overview: str | None = None,
    memories: Sequence[str] = (),
    related: Sequence[RelatedQA] = (),
    summary: str = "",
    history: Sequence[Message] = (),
    history_max_chars: int = 1200,
) -> list[BaseMessage]:
    """Layered prompt: rules → who the user is → repo overview → past findings → code → conversation."""
    sections = [RULES]
    if memories:
        sections.append(
            "What you know about the user (personalize tone and depth; never mention this list):\n"
            + "\n".join(f"- {m}" for m in memories)
        )
    if overview:
        sections.append(f"Repository overview:\n{overview}")
    if related:
        sections.append(
            "Relevant answers from the user's earlier conversations about this repository:\n"
            + "\n\n".join(f"Q: {r.question}\nA: {_clip(r.answer, 800)}" for r in related)
        )
    if summary:
        sections.append(f"Summary of the earlier part of this conversation:\n{summary}")
    sections.append(f"Retrieved code context:\n{format_docs(docs) or '(nothing relevant found)'}")

    messages: list[BaseMessage] = [SystemMessage("\n\n".join(sections))]
    for m in history:
        content = _clip(m.content, history_max_chars)
        messages.append(HumanMessage(content) if m.role == "user" else AIMessage(content))
    messages.append(HumanMessage(question))
    return messages


def generate_answer(question: str, docs: Sequence[Document], **context) -> str:
    return StrOutputParser().invoke(get_llm().invoke(build_messages(question, docs, **context)))
