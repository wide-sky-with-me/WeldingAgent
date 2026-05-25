import pytest
from pydantic import ValidationError

from pwps_agent.core.contracts import Evidence
from pwps_agent.core.quality import DraftQualityReport, FieldCoverageReport
from pwps_agent.core.state import PWPSState, create_initial_state
from pwps_agent.core.state_merge import merge_state_patch
from pwps_agent.tools.draft_verifier import verify_draft_quality


def test_quality_report_is_serializable_on_state() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        interaction_mode="auto_draft",
        run_id="quality_contract",
    )
    report = DraftQualityReport(
        quality_level="partial",
        recommended_action="refine_search",
        field_counts={"filled": 7, "candidate": 2, "suggested": 2, "missing": 30},
        critical_missing_fields=["filler_material", "polarity", "preheat_temperature"],
        weak_evidence_fields=["current_range"],
        low_quality_sources=["https://www.facebook.com/example"],
        blocked_inference_violations=[],
        refinement_focus_fields=["filler_material", "polarity"],
        human_review_fields=["filler_material", "polarity", "preheat_temperature"],
        mode_guidance="auto_refine",
        target_field_coverage=[
            FieldCoverageReport(
                query_id="kq_002",
                target_fields=["filler_material", "filler_diameter"],
                covered_fields=[],
                missing_target_fields=["filler_material", "filler_diameter"],
            )
        ],
    )

    updated = merge_state_patch(state, {"quality_report": report.model_dump()})

    assert updated.quality_report is not None
    assert updated.quality_report["recommended_action"] == "refine_search"
    assert updated.quality_report["human_review_fields"] == [
        "filler_material",
        "polarity",
        "preheat_temperature",
    ]
    assert updated.model_dump()["quality_report"]["quality_level"] == "partial"


def test_invalid_quality_report_patch_records_warning_and_preserves_existing_report() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="auto_draft",
        run_id="invalid_quality_contract",
    )
    existing_report = DraftQualityReport(
        quality_level="partial",
        recommended_action="refine_search",
    ).model_dump()
    state = merge_state_patch(state, {"quality_report": existing_report})

    updated = merge_state_patch(
        state,
        {
            "quality_report": {
                "quality_level": "unsupported",
                "recommended_action": "refine_search",
            }
        },
    )

    assert updated.quality_report == existing_report
    warnings = [
        entry for entry in updated.trace if entry["node"] == "state_merge"
    ]
    assert warnings[-1]["event_type"] == "merge_warning"
    assert warnings[-1]["payload"]["key"] == "quality_report"


def test_invalid_quality_report_is_rejected_at_state_boundary() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="auto_draft",
        run_id="invalid_quality_state",
    )
    payload = state.model_dump()
    payload["quality_report"] = {
        "quality_level": "unsupported",
        "recommended_action": "refine_search",
    }

    with pytest.raises(ValidationError):
        PWPSState.model_validate(payload)


def test_invalid_refinement_counter_patches_record_warning_and_preserve_values() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="auto_draft",
        run_id="invalid_quality_counters",
    )
    state.refinement_attempts = 1
    state.max_refinement_attempts = 3

    updated = merge_state_patch(
        state,
        {
            "refinement_attempts": -1,
            "max_refinement_attempts": 0,
        },
    )
    updated = merge_state_patch(
        updated,
        {
            "refinement_attempts": True,
            "max_refinement_attempts": False,
        },
    )

    assert updated.refinement_attempts == 1
    assert updated.max_refinement_attempts == 3
    warnings = [
        entry for entry in updated.trace if entry["node"] == "state_merge"
    ]
    assert [warning["payload"]["key"] for warning in warnings[-4:]] == [
        "refinement_attempts",
        "max_refinement_attempts",
        "refinement_attempts",
        "max_refinement_attempts",
    ]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("refinement_attempts", -1),
        ("refinement_attempts", True),
        ("max_refinement_attempts", 0),
        ("max_refinement_attempts", False),
    ],
)
def test_invalid_refinement_counters_are_rejected_at_state_boundary(
    field_name: str,
    value: object,
) -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="auto_draft",
        run_id="invalid_quality_counter_state",
    )
    payload = state.model_dump()
    payload[field_name] = value

    with pytest.raises(ValidationError):
        PWPSState.model_validate(payload)


def test_verifier_recommends_refinement_for_uncovered_critical_fields() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW butt joint flat position AWS D1.1 pWPS draft",
        interaction_mode="auto_draft",
        run_id="quality_refine",
    )
    state.knowledge_queries = [
        {
            "query_id": "kq_002",
            "target_fields": ["filler_material", "polarity", "preheat_temperature"],
        }
    ]
    for field_id, value in {
        "applicable_standard": "AWS D1.1",
        "base_material": "Q355B",
        "thickness": "12 mm",
        "workpiece_type": "plate",
        "welding_process": "GMAW",
        "joint_type": "butt joint",
        "welding_position": "flat",
    }.items():
        state.fields[field_id].value = value
        state.fields[field_id].status = "filled"
        state.fields[field_id].source = {"type": "user_input"}

    result = verify_draft_quality(state)

    report = result.state_patch["quality_report"]
    assert result.success is True
    assert report["recommended_action"] == "refine_search"
    assert report["mode_guidance"] == "auto_refine"
    assert "filler_material" in report["critical_missing_fields"]
    assert report["target_field_coverage"][0]["missing_target_fields"] == [
        "filler_material",
        "polarity",
        "preheat_temperature",
    ]


def test_verifier_detects_blocked_metadata_inference() -> None:
    state = create_initial_state(
        user_input="Q355B GMAW",
        interaction_mode="auto_draft",
        run_id="blocked_metadata",
    )
    state.fields["project_name"].value = "Bridge Project"
    state.fields["project_name"].status = "suggested"
    state.fields["project_name"].source = {"type": "model_fallback"}

    result = verify_draft_quality(state)

    report = result.state_patch["quality_report"]
    assert "project_name" in report["blocked_inference_violations"]
    assert report["recommended_action"] == "synthesize_with_limitations"
    assert report["mode_guidance"] == "auto_suggest_with_limitations"
    assert "project_name" in report["human_review_fields"]


def test_verifier_flags_weak_evidence_and_low_quality_sources() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="guided_confirmation",
        run_id="weak_evidence",
    )
    state.evidence.append(
        Evidence(
            evidence_id="ev_social_1",
            source_type="web",
            source_ref="https://forum.example.com/facebook.com/wps",
            content="Forum repost claims ER50-6 with CO2.",
            related_fields=["filler_material", "shielding_gas"],
            source_tier="webpage",
            reliability="low",
            confidence="low",
        )
    )
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    state.fields["filler_material"].evidence_ids = ["ev_social_1"]
    state.fields["filler_material"].source = {
        "type": "web",
        "evidence_ids": ["ev_social_1"],
    }
    state.fields["shielding_gas"].value = "CO2"
    state.fields["shielding_gas"].status = "suggested"
    state.fields["shielding_gas"].evidence_ids = []
    state.fields["shielding_gas"].source = {"type": "llm", "evidence_ids": []}

    result = verify_draft_quality(state)

    report = result.state_patch["quality_report"]
    assert report["mode_guidance"] == "ask_user_for_confirmation"
    assert report["weak_evidence_fields"] == ["filler_material", "shielding_gas"]
    assert report["low_quality_sources"] == [
        "https://forum.example.com/facebook.com/wps"
    ]
    assert "filler_material" in report["human_review_fields"]
    assert report["evidence_quality"]["by_source_tier"]["webpage"] == 1


def test_guided_verifier_marks_strong_candidate_for_human_review() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="guided_confirmation",
        run_id="guided_strong_candidate",
    )
    state.evidence.append(
        Evidence(
            evidence_id="ev_official_1",
            source_type="local_doc",
            source_ref="data/local_docs/q355b_wps.md",
            content="Local procedure reference lists ER50-6 filler.",
            related_fields=["filler_material"],
            source_tier="official_standard",
            reliability="high",
            confidence="high",
        )
    )
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    state.fields["filler_material"].evidence_ids = ["ev_official_1"]
    state.fields["filler_material"].source = {
        "type": "local_doc",
        "evidence_ids": ["ev_official_1"],
    }

    result = verify_draft_quality(state)

    report = result.state_patch["quality_report"]
    assert "filler_material" not in report["weak_evidence_fields"]
    assert "filler_material" in report["human_review_fields"]
    assert report["mode_guidance"] == "ask_user_for_confirmation"


def test_verifier_field_counts_include_zero_count_status_categories() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW",
        interaction_mode="auto_draft",
        run_id="stable_field_counts",
    )
    state.fields["base_material"].value = "Q355B"
    state.fields["base_material"].status = "filled"

    result = verify_draft_quality(state)

    report = result.state_patch["quality_report"]
    assert report["field_counts"]["filled"] == 1
    assert report["field_counts"]["candidate"] == 0
    assert report["field_counts"]["suggested"] == 0
    assert report["field_counts"]["missing"] > 0
    assert report["field_counts"]["need_confirmation"] == 0
    assert report["field_counts"]["conflict"] == 0
    assert report["field_counts"]["user_confirmed"] == 0


def test_pipe_workpiece_missing_diameter_is_critical() -> None:
    state = create_initial_state(
        user_input="Q355B pipe GMAW AWS D1.1 pWPS draft",
        interaction_mode="auto_draft",
        run_id="pipe_missing_diameter",
    )
    _fill_required_draft_fields(state, workpiece_type="pipe", include_diameter=False)

    result = verify_draft_quality(state)

    report = result.state_patch["quality_report"]
    assert "diameter" in report["critical_missing_fields"]
    assert report["recommended_action"] == "refine_search"


def test_plate_workpiece_missing_diameter_is_not_critical() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW AWS D1.1 pWPS draft",
        interaction_mode="auto_draft",
        run_id="plate_missing_diameter",
    )
    _fill_required_draft_fields(state, workpiece_type="plate", include_diameter=False)

    result = verify_draft_quality(state)

    report = result.state_patch["quality_report"]
    assert "diameter" not in report["critical_missing_fields"]
    assert report["recommended_action"] == "synthesize"


def test_guided_verifier_synthesizes_when_no_human_review_fields() -> None:
    state = create_initial_state(
        user_input="Q355B 12mm plate GMAW AWS D1.1 pWPS draft",
        interaction_mode="guided_confirmation",
        run_id="guided_clean_synthesize",
    )
    _fill_required_draft_fields(state, workpiece_type="plate", include_diameter=False)

    result = verify_draft_quality(state)

    report = result.state_patch["quality_report"]
    assert report["recommended_action"] == "synthesize"
    assert report["human_review_fields"] == []
    assert report["mode_guidance"] == "guided_synthesize"


def _fill_required_draft_fields(
    state: PWPSState,
    *,
    workpiece_type: str,
    include_diameter: bool,
) -> None:
    values = {
        "applicable_standard": "AWS D1.1",
        "base_material": "Q355B",
        "thickness": "12 mm",
        "workpiece_type": workpiece_type,
        "welding_process": "GMAW",
        "joint_type": "butt joint",
        "welding_position": "flat",
        "filler_material": "ER50-6",
        "shielding_gas": "CO2",
        "polarity": "DCEP",
        "current_range": "180-220 A",
        "voltage_range": "22-26 V",
        "preheat_temperature": "not specified",
        "interpass_temperature": "150 C max",
    }
    if include_diameter:
        values["diameter"] = "219 mm"

    for field_id, value in values.items():
        state.fields[field_id].value = value
        state.fields[field_id].status = "filled"
        state.fields[field_id].source = {"type": "user_input"}
