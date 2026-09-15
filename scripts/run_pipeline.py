import argparse
import sys

sys.path.insert(0, ".")

from src.services.exceptions import RepoIndexingError, RepoNotIndexedError
from src.services.qa_service import ask_question, index_repository


def main():
    parser = argparse.ArgumentParser(description="Index a GitHub repo and ask a question about it.")
    parser.add_argument("repo_url", help="URL of the public GitHub repository")
    parser.add_argument("question", help="Question to ask about the repository")
    parser.add_argument("--force-reindex", action="store_true", help="Rebuild the index even if one exists")
    args = parser.parse_args()

    try:
        index_result = index_repository(args.repo_url, args.force_reindex)
    except RepoIndexingError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    if index_result.reused_existing:
        print(f"Reusing existing index for {args.repo_url}")
    else:
        print(f"Indexed {args.repo_url} ({index_result.num_chunks} chunks)")

    print("\nAnswering question ...\n")
    try:
        result = ask_question(args.repo_url, args.question)
    except RepoNotIndexedError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    print("Answer:")
    print(result.answer)
    print("\nSources:")
    for source in result.sources:
        print(f"  - {source}")


if __name__ == "__main__":
    main()
