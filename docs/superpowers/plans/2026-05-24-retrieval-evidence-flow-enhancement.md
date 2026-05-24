# Retrieval And Evidence Flow Enhancement Plan

**Date:** 2026-05-24

**Goal:** Complete the stage-2 retrieval and evidence flow enhancements for the pWPS auto-draft slice: model-planned search queries, safer multi-provider web search, source-tiered evidence confidence, and persisted evidence-to-field audit data.

**Architecture:** Keep query generation in `knowledge_planning`; keep web provider adapters under `knowledge/`; keep evidence conversion as structured `Evidence`; persist audit/reuse data as run artifacts without introducing a database or hard-coded welding rule engine.

**Status:** Completed. The repository now has model-planned search before provider execution, Tavily/Brave adapters with instance-level query caching and transient-error retry/backoff, source-tiered web evidence classification, and an `evidence_index.json` artifact that records search context plus evidence-to-field and field-to-evidence mappings.

## Completed Work

- [x] Confirm `auto_draft` calls `knowledge_planning` before web search and uses planned query text.
- [x] Add provider-level cache settings and instance query-response caching for Tavily/Brave.
- [x] Add configurable transient retry/backoff for provider HTTP calls.
- [x] Avoid retrying non-transient HTTP authorization failures.
- [x] Add `Evidence.source_tier` and `Evidence.confidence`.
- [x] Classify web evidence as `official_standard`, `textbook`, or `webpage` with corresponding reliability/confidence.
- [x] Persist `evidence_index.json` with search context, evidence records, `evidence_to_fields`, and `field_to_evidence`.
- [x] Add regression tests for provider caching, retry/backoff, non-transient HTTP handling, evidence source tiers, and evidence index persistence.

## Verification

```text
uv run pytest tests/test_knowledge_planning.py tests/test_web_search_provider.py tests/test_evidence_reasoning.py tests/test_state_merge.py tests/test_auto_draft_workflow.py tests/test_graph_retry.py -q
22 passed, 1 warning

uv run pytest -q
49 passed, 1 warning

uv run python -m compileall -q src tests
passed
```
