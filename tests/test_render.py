from pwps_agent.core.modes import confirm_fields
from pwps_agent.core.state import create_initial_state
from pwps_agent.render.markdown import render_field_report, render_pwps_draft


def test_render_draft_shows_status_and_missing_fields() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="auto_draft",
    )
    state.fields["base_material"].value = "Q355B"
    state.fields["base_material"].status = "filled"
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    state.fields["preheat_temperature"].status = "need_confirmation"

    markdown = render_pwps_draft(state)

    assert "# pWPS 草案" in markdown
    assert "母材牌号" in markdown
    assert "Q355B" in markdown
    assert "candidate" in markdown
    assert "待确认项与风险提示" in markdown


def test_render_field_report_lists_user_confirmed_fields() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="guided_confirmation",
    )
    state = confirm_fields(
        state,
        field_values={"filler_material": "ER50-6"},
        user_message="Confirm ER50-6.",
    )

    report = render_field_report(state)

    assert "user_confirmed_fields" in report
    assert "filler_material" in report["user_confirmed_fields"]


def test_render_field_report_lists_retained_candidates_on_filled_fields() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="auto_draft",
    )
    state.fields["base_material"].value = "Q355B"
    state.fields["base_material"].status = "filled"
    state.fields["base_material"].candidates.append(
        {
            "value": "ASTM A572 Grade 50",
            "status": "candidate",
            "evidence_ids": ["ev_1"],
            "note": "Possible standard mapping from web evidence.",
        }
    )

    report = render_field_report(state)

    assert report["retained_candidates"]["base_material"][0]["value"] == "ASTM A572 Grade 50"


def test_render_draft_uses_structured_sections_when_present() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="auto_draft",
    )
    state.sections = {
        "A": {
            "title": "文件与项目元信息",
            "fields": [
                {
                    "field_id": "project_name",
                    "label": "项目名称",
                    "value": "待确认",
                    "status": "missing",
                    "confidence": "unknown",
                    "evidence_ids": [],
                    "source": None,
                    "note": "",
                }
            ],
        }
    }

    markdown = render_pwps_draft(state)

    assert "项目名称" in markdown
    assert "confidence=unknown" in markdown


def test_draft_renders_quality_summary_and_limits_missing_noise() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        interaction_mode="auto_draft",
        run_id="render_quality",
    )
    state.quality_report = {
        "quality_level": "partial",
        "recommended_action": "synthesize_with_limitations",
        "field_counts": {"filled": 7, "candidate": 3, "suggested": 4, "missing": 27},
        "critical_missing_fields": ["preheat_temperature", "interpass_temperature"],
        "weak_evidence_fields": ["current_range"],
        "low_quality_sources": [],
        "blocked_inference_violations": [],
        "refinement_focus_fields": [],
        "target_field_coverage": [],
        "evidence_quality": {"evidence_count": 4, "by_source_tier": {"webpage": 4}},
        "notes": ["Refinement attempts exhausted."],
    }

    draft = render_pwps_draft(state)

    assert "草案质量摘要" in draft
    assert "preheat_temperature" in draft
    assert "project_name" not in draft.split("待确认项与风险提示")[-1]
