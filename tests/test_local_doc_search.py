from pathlib import Path

from pwps_agent.config import load_settings
from pwps_agent.core.state import create_initial_state
from pwps_agent.knowledge.local_doc_provider import LocalDocumentProvider
from pwps_agent.tools.evidence import search_results_to_evidence
from pwps_agent.tools.local_doc_search import search_local_documents


FIXTURE_DIR = Path("tests/fixtures/local_docs")


def test_local_doc_search_uses_local_doc_preferred_queries() -> None:
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")
    state.knowledge_queries = [
        {
            "query_id": "kq_local",
            "query_text": "Q355B GMAW ER50-6",
            "preferred_sources": ["local_doc"],
        },
        {
            "query_id": "kq_web",
            "query_text": "Q355B web query",
            "preferred_sources": ["web"],
        },
    ]
    provider = LocalDocumentProvider(FIXTURE_DIR)

    result = search_local_documents(state, provider)

    assert result.success is True
    assert result.state_patch["search_results"]
    assert result.state_patch["search_results"][0]["source_type"] == "local_doc"
    assert result.state_patch["evidence"][0]["source_type"] == "local_doc"
    assert "Retrieved" in result.summary


def test_local_doc_evidence_preserves_local_doc_source_type() -> None:
    provider = LocalDocumentProvider(FIXTURE_DIR)
    results = provider.search("Q355B GMAW ER50-6", query_id="kq_local")

    evidence = search_results_to_evidence(results)

    assert evidence[0].source_type == "local_doc"
    assert evidence[0].source_tier == "textbook"
    assert evidence[0].reliability == "medium"
    assert evidence[0].source_ref.endswith("q355b_gmaw_wps.md")


def test_settings_loads_local_doc_max_results(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LOCAL_DOC_MAX_RESULTS=7\nPWPS_LOCAL_DOCS_DIR=/tmp/local-docs\n", encoding="utf-8")

    settings = load_settings(env_file)

    assert settings.local_docs.max_results == 7
    assert settings.paths.local_docs_dir == Path("/tmp/local-docs")
