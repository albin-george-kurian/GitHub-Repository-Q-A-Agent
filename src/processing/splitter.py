from itertools import groupby

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.ingestion.file_filter import LANGUAGE_BY_EXTENSION


def split_documents(documents: list[Document], chunk_size: int, chunk_overlap: int) -> list[Document]:
    """Split documents into chunks, using a language-aware splitter for known code extensions
    and a generic splitter for everything else (docs, config, unrecognized code)."""
    chunks: list[Document] = []

    documents = sorted(documents, key=lambda d: d.metadata.get("extension", ""))
    for extension, group in groupby(documents, key=lambda d: d.metadata.get("extension", "")):
        group_docs = list(group)
        language = LANGUAGE_BY_EXTENSION.get(extension)

        if language is not None:
            splitter = RecursiveCharacterTextSplitter.from_language(
                language=language, chunk_size=chunk_size, chunk_overlap=chunk_overlap
            )
        else:
            splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        chunks.extend(splitter.split_documents(group_docs))

    return chunks
