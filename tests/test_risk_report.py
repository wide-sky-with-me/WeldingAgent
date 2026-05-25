from pwps_agent.core.contracts import Evidence
from pwps_agent.core.state import create_initial_state
from pwps_agent.tools.risk_report import generate_risk_report


def test_risk_report_flags_missing_low_confidence_and_thermal_fields() -> None:
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")
    state.fields["base_material"].value = "Q355B"
    state.fields["base_material"].status = "filled"
    state.fields["base_material"].confidence = "low"
    state.fields["pwht"].status = "missing"

    result = generate_risk_report(state)

    report = result.state_patch["field_report"]
    risks = result.state_patch["risks"]
    assert "pwht" in report["missing_fields"]
    assert any(risk["field_id"] == "base_material" and risk["risk_type"] == "low_confidence" for risk in risks)
    assert any(risk["field_id"] == "pwht" and risk["risk_type"] == "thermal_control" for risk in risks)


def test_risk_report_marks_web_reference_only_candidate_wording() -> None:
    state = create_initial_state("Q355B 12mm GMAW", "auto_draft")
    state.evidence.append(
        Evidence(
            evidence_id="ev_web_1",
            source_type="web",
            content="ER50-6 appears in a web WPS example.",
            reliability="low",
        )
    )
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    state.fields["filler_material"].confidence = "low"
    state.fields["filler_material"].evidence_ids = ["ev_web_1"]
    state.fields["filler_material"].source = {"type": "web", "evidence_ids": ["ev_web_1"]}

    result = generate_risk_report(state)

    risks = result.state_patch["risks"]
    assert any(risk["field_id"] == "filler_material" and risk["risk_type"] == "web_reference_only" for risk in risks)
    assert any("reference only" in risk["message"] for risk in risks)
