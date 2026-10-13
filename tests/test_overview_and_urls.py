import pytest
from langchain_core.documents import Document

from src.ingestion.repo_url import normalize_repo_url
from src.rag import overview
from src.services.exceptions import InvalidRepoUrlError


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/PSF/Requests",
        "https://github.com/psf/requests/",
        "https://www.github.com/psf/requests.git",
        "  http://github.com/psf/requests  ",
    ],
)
def test_repo_urls_normalize_to_one_key(url):
    assert normalize_repo_url(url) == "https://github.com/psf/requests"


@pytest.mark.parametrize("url", ["https://gitlab.com/a/b", "https://github.com/onlyowner", "not a url"])
def test_non_github_urls_are_rejected(url):
    with pytest.raises(InvalidRepoUrlError):
        normalize_repo_url(url)


def test_layout_groups_files_by_directory():
    layout = overview.summarize_layout(["README.md", "src/a.py", "src/b.py", "src/pkg/deep/c.py", "docs/x.md"])
    assert layout.splitlines() == ["docs/ (1 file)", "src/ (2 files)", "src/pkg/ (1 file)", "README.md"]


def test_overview_falls_back_to_readme_when_llm_fails(monkeypatch):
    def broken():
        raise RuntimeError("no key")

    monkeypatch.setattr(overview, "get_llm", broken)
    docs = [
        Document(page_content="# Widgets\nSigns things.", metadata={"source": "README.md"}),
        Document(page_content="x = 1", metadata={"source": "src/a.py"}),
    ]
    text = overview.build_overview(docs)
    assert "## README excerpt\n# Widgets\nSigns things." in text
    assert "src/ (1 file)" in text
