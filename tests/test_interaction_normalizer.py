from pwps_agent.core.interaction import (
    InteractionOption,
    InteractionQuestion,
    InteractionRequest,
)
from pwps_agent.interaction.normalizer import normalize_interaction_response


def _guided_interaction() -> dict:
    return InteractionRequest(
        request_id="run1:guided_field_confirmation:1",
        interaction_mode="guided_confirmation",
        purpose="guided_field_confirmation",
        title="Confirm welding choices",
        summary="Choose a candidate.",
        questions=[
            InteractionQuestion(
                question_id="confirm_filler_metal",
                field_ids=["filler_metal"],
                prompt="Confirm filler metal.",
                input_kind="single_choice",
                options=[
                    InteractionOption(
                        value="ER50-6",
                        label="ER50-6 solid wire",
                        evidence_ids=["ev1", "ev2"],
                        field_updates={"filler_metal": "ER50-6"},
                    ),
                    InteractionOption(
                        value="ER49-1",
                        label="ER49-1 solid wire",
                        evidence_ids=["ev3"],
                        field_updates={"filler_metal": "ER49-1"},
                    ),
                ],
            )
        ],
    ).model_dump()


def test_option_number_selects_first_option_updates_and_evidence():
    payload = normalize_interaction_response(_guided_interaction(), "1")

    assert payload["request_id"] == "run1:guided_field_confirmation:1"
    assert payload["fields"] == {"filler_metal": "ER50-6"}
    assert payload["selected_options"] == [
        {
            "question_id": "confirm_filler_metal",
            "option_index": 1,
            "value": "ER50-6",
            "label": "ER50-6 solid wire",
            "field_updates": {"filler_metal": "ER50-6"},
        }
    ]
    assert payload["evidence_ids_shown"] == ["ev1", "ev2"]
    assert payload["unresolved_text"] == ""


def test_comma_separated_field_value_pairs_parse_into_fields():
    payload = normalize_interaction_response(
        _guided_interaction(),
        "base_material=Q355B, thickness=12mm, welding_process=GMAW",
    )

    assert payload["fields"] == {
        "base_material": "Q355B",
        "thickness": "12mm",
        "welding_process": "GMAW",
    }
    assert payload["selected_options"] == []
    assert payload["unresolved_text"] == ""


def test_exact_option_label_or_value_selects_option():
    by_label = normalize_interaction_response(
        _guided_interaction(),
        "ER50-6 solid wire",
    )
    by_value = normalize_interaction_response(_guided_interaction(), "ER50-6")

    assert by_label["fields"] == {"filler_metal": "ER50-6"}
    assert by_value["fields"] == {"filler_metal": "ER50-6"}
    assert by_label["selected_options"][0]["question_id"] == "confirm_filler_metal"
    assert by_value["selected_options"][0]["option_index"] == 1


def test_free_form_text_remains_unresolved_without_fields():
    payload = normalize_interaction_response(
        _guided_interaction(),
        "I need to check the project WPS notes first.",
    )

    assert payload["fields"] == {}
    assert payload["selected_options"] == []
    assert payload["message"] == "I need to check the project WPS notes first."
    assert payload["unresolved_text"] == "I need to check the project WPS notes first."
