"""A per-repo overview, generated once at index time and included in every prompt.

Similarity search only ever sees a handful of chunks, so big-picture questions
("what does this project do?", "how is it structured?") need this map of the repo."""

import logging
import posixpath
import re
from collections import Counter

from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import StrOutputParser

from src.llm.groq_client import get_llm

logger = logging.getLogger(__name__)

_README = re.compile(r"^readme(\.\w+)?$", re.IGNORECASE)
_MANIFESTS = (
    "pyproject.toml", "setup.cfg", "requirements.txt", "package.json", "tsconfig.json",
    "Cargo.toml", "pom.xml", "composer.json", "Gemfile",
)


def summarize_layout(paths: list[str], max_entries: int = 80) -> str:
    """Directory-level map: files at the root, and file counts per directory (two levels deep)."""
    root_files: list[str] = []
    dir_counts: Counter[str] = Counter()
    for path in paths:
        directory = posixpath.dirname(path)
        if not directory:
            root_files.append(path)
        else:
            dir_counts["/".join(directory.split("/")[:2]) + "/"] += 1

    lines = [f"{d} ({n} file{'s' if n != 1 else ''})" for d, n in sorted(dir_counts.items())]
    lines += sorted(root_files)
    if len(lines) > max_entries:
        lines = lines[:max_entries] + [f"… and {len(lines) - max_entries} more"]
    return "\n".join(lines)


def _find_readme(documents: list[Document]) -> str:
    for doc in sorted(documents, key=lambda d: len(d.metadata["source"])):
        if "/" not in doc.metadata["source"] and _README.match(doc.metadata["source"]):
            return doc.page_content
    return ""


def build_overview(documents: list[Document]) -> str:
    """Markdown overview: an LLM-written summary when possible, plus the directory layout.
    Falls back to a README excerpt if the LLM is unavailable, so indexing never fails on it."""
    paths = sorted(doc.metadata["source"] for doc in documents)
    layout = summarize_layout(paths)
    readme = _find_readme(documents)

    try:
        summary = _llm_summary(documents, readme, layout)
        return f"## Summary\n{summary}\n\n## Layout\n{layout}"
    except Exception as exc:  # missing key, rate limit, network: degrade gracefully
        logger.warning("Overview LLM summary unavailable, using README excerpt: %s", exc)
        excerpt = readme[:1500].strip() or "(no README found)"
        return f"## README excerpt\n{excerpt}\n\n## Layout\n{layout}"


def _llm_summary(documents: list[Document], readme: str, layout: str) -> str:
    by_path = {doc.metadata["source"]: doc.page_content for doc in documents}
    manifests = [f"### {name}\n{by_path[name][:1500]}" for name in _MANIFESTS if name in by_path][:3]

    material = f"## Directory layout\n{layout}\n\n## README\n{readme[:4000] or '(none)'}"
    if manifests:
        material += "\n\n## Manifests\n" + "\n\n".join(manifests)

    result = get_llm().invoke(
        [
            SystemMessage(
                "You write a concise orientation for a code repository, for an assistant that will answer "
                "questions about it. Cover: what the project does, tech stack, how the code is organized "
                "(key directories/modules and their roles), and entry points. Use only the material given; "
                "don't guess. Max 250 words, markdown bullets welcome, no title."
            ),
            HumanMessage(material),
        ]
    )
    return StrOutputParser().invoke(result).strip()
