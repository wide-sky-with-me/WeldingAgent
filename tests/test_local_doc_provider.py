from pathlib import Path

from pwps_agent.knowledge.local_doc_provider import LocalDocumentProvider


FIXTURE_DIR = Path("tests/fixtures/local_docs")


def test_local_doc_provider_returns_ranked_matching_snippets() -> None:
    provider = LocalDocumentProvider(FIXTURE_DIR, max_results=3)

    results = provider.search("Q355B GMAW ER50-6 shielding gas", query_id="kq_local_1")

    assert results
    assert results[0].source_type == "local_doc"
    assert results[0].provider == "local_doc"
    assert results[0].query_id == "kq_local_1"
    assert results[0].result_id.startswith("kq_local_1_local_")
    assert "q355b_gmaw_wps.md" in (results[0].url or "")
    assert "ER50-6" in results[0].snippet
    assert results[0].score is not None


def test_local_doc_provider_ignores_unsupported_files_and_empty_queries(tmp_path: Path) -> None:
    (tmp_path / "ignored.bin").write_bytes(b"\x00\x01")
    (tmp_path / "doc.md").write_text("Q355B document.", encoding="utf-8")
    provider = LocalDocumentProvider(tmp_path)

    assert provider.search("", query_id="empty") == []
    assert provider.search("Q355B", query_id="kq_local_2")[0].title == "doc.md"


def test_local_doc_provider_missing_directory_returns_no_results(tmp_path: Path) -> None:
    provider = LocalDocumentProvider(tmp_path / "missing")

    assert provider.search("Q355B", query_id="kq_local_3") == []
