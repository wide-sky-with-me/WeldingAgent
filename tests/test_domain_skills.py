from pathlib import Path

import pytest

from pwps_agent.agent.prompt_loader import (
    load_domain_skill,
    load_domain_skill_bundle,
    load_prompt,
)


def test_load_domain_skill_reads_named_markdown_guidance() -> None:
    skill = load_domain_skill("pwps_auto_draft")

    assert skill.name == "pwps_auto_draft"
    assert "auto_draft" in skill.content
    assert "Domain Skill" in skill.content
    assert "Runtime Tools" in skill.content


def test_load_domain_skill_rejects_path_separators(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Domain skill name"):
        load_domain_skill("../pwps_auto_draft", skill_dir=tmp_path)


def test_load_domain_skill_bundle_formats_ordered_supervisor_context() -> None:
    bundle = load_domain_skill_bundle(
        ["pwps_evidence_handling", "pwps_risk_review"],
    )

    assert bundle.startswith("# Domain Skill Context")
    assert "## Domain Skill: pwps_evidence_handling" in bundle
    assert "## Domain Skill: pwps_risk_review" in bundle
    assert bundle.index("pwps_evidence_handling") < bundle.index("pwps_risk_review")


def test_prompt_and_skill_loading_do_not_depend_on_current_working_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    prompt = load_prompt("requirement_understanding")
    skill = load_domain_skill("pwps_auto_draft")

    assert "welding requirement" in prompt.lower()
    assert skill.name == "pwps_auto_draft"
    assert "Domain Skill" in skill.content


def test_supervisor_prompts_are_loaded_from_prompt_directory() -> None:
    base_prompt = load_prompt("supervisor")
    auto_mode_prompt = load_prompt("supervisor_mode_auto_draft")
    guided_mode_prompt = load_prompt("supervisor_mode_guided_confirmation")

    assert "LLM Supervisor" in base_prompt
    assert "do not ask the user except" in auto_mode_prompt
    assert "ask the user" in guided_mode_prompt
