from pwps_agent.core.state import create_initial_state
from pwps_agent.tools.section_generation import generate_sections


def test_generate_sections_preserves_field_status_source_evidence_and_confidence() -> None:
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")
    state.fields["base_material"].value = "Q355B"
    state.fields["base_material"].status = "filled"
    state.fields["base_material"].confidence = "high"
    state.fields["base_material"].source = {"type": "user_input", "ref": "ev_user_input_1"}
    state.fields["base_material"].evidence_ids = ["ev_user_input_1"]

    result = generate_sections(state)

    assert result.success is True
    sections = result.state_patch["sections"]
    base_material = next(
        field for field in sections["B"]["fields"] if field["field_id"] == "base_material"
    )
    assert base_material["value"] == "Q355B"
    assert base_material["status"] == "filled"
    assert base_material["confidence"] == "high"
    assert base_material["source"] == {"type": "user_input", "ref": "ev_user_input_1"}
    assert base_material["evidence_ids"] == ["ev_user_input_1"]


def test_generate_sections_keeps_unknown_project_metadata_uninvented() -> None:
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")

    result = generate_sections(state)

    sections = result.state_patch["sections"]
    project_name = next(
        field for field in sections["A"]["fields"] if field["field_id"] == "project_name"
    )
    client = next(field for field in sections["A"]["fields"] if field["field_id"] == "client")
    assert project_name["value"] == "待确认"
    assert client["value"] == "待确认"
    assert project_name["status"] == "missing"
