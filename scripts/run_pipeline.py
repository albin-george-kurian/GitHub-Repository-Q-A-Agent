import argparse
import sys

sys.path.insert(0, ".")

from src.config import settings
from src.embeddings.embedding_provider import get_embeddings
from src.ingestion.document_loader import load_repo_documents
from src.ingestion.repo_loader import clone_repo, cleanup_repo
from src.processing.splitter import split_documents
from src.rag.qa_chain import answer_question, build_qa_chain
from src.vectorstore.faiss_store import build_and_save_index, index_exists, load_index


def get_vector_store(repo_url: str, force_reindex: bool):
    embeddings = get_embeddings()

    if index_exists(repo_url) and not force_reindex:
        print(f"Reusing existing index for {repo_url}")
        return load_index(repo_url, embeddings)

    print(f"Cloning {repo_url} ...")
    local_path = clone_repo(repo_url)
    try:
        print("Loading and filtering files ...")
        documents = load_repo_documents(local_path, settings.max_file_size_bytes)
        print(f"Loaded {len(documents)} files. Splitting into chunks ...")
        chunks = split_documents(documents, settings.chunk_size, settings.chunk_overlap)
        print(f"Created {len(chunks)} chunks. Building embeddings + FAISS index ...")
        return build_and_save_index(repo_url, chunks, embeddings)
    finally:
        cleanup_repo(local_path)


def main():
    parser = argparse.ArgumentParser(description="Index a GitHub repo and ask a question about it.")
    parser.add_argument("repo_url", help="URL of the public GitHub repository")
    parser.add_argument("question", help="Question to ask about the repository")
    parser.add_argument("--force-reindex", action="store_true", help="Rebuild the index even if one exists")
    args = parser.parse_args()

    vector_store = get_vector_store(args.repo_url, args.force_reindex)
    chain = build_qa_chain(vector_store, settings.retriever_top_k)

    print("\nAnswering question ...\n")
    result = answer_question(chain, args.question)

    print("Answer:")
    print(result["answer"])
    print("\nSources:")
    for source in result["sources"]:
        print(f"  - {source}")


if __name__ == "__main__":
    main()
