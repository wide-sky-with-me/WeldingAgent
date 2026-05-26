from __future__ import annotations

from io import StringIO

from pwps_agent.interaction.terminal import (
    collect_terminal_response,
    render_terminal_interaction,
)


def _interaction() -> dict:
    return {
        "title": "Confirm welding choices",
        "summary": "Review the proposed candidate.",
        "assistant_message": "The agent recommends the first option.",
        "questions": [
            {
                "question_id": "confirm_filler_material",
                "field_ids": ["filler_material"],
                "prompt": "Confirm filler material.",
                "input_kind": "single_choice",
                "options": [
                    {
                        "value": "ER50-6",
                        "label": "ER50-6 solid wire",
                        "recommended": True,
                        "suitability": "Matches common GMAW carbon steel practice.",
                        "risk_note": "Verify against qualified procedure limits.",
                    },
                    {
                        "value": "ER49-1",
                        "label": "ER49-1 solid wire",
                        "recommended": False,
                    },
                ],
            }
        ],
    }


def test_render_terminal_interaction_includes_prompt_and_option_details() -> None:
    text = render_terminal_interaction(_interaction())

    assert "[需要用户输入] Confirm welding choices" in text
    assert "Review the proposed candidate." in text
    assert "The agent recommends the first option." in text
    assert "Confirm filler material." in text
    assert "1. ER50-6 solid wire [推荐]" in text
    assert "适用性: Matches common GMAW carbon steel practice." in text
    assert "风险: Verify against qualified procedure limits." in text
    assert "2. ER49-1 solid wire" in text


def test_collect_terminal_response_prints_interaction_and_returns_raw_line() -> None:
    stdout = StringIO()
    response = collect_terminal_response(_interaction(), StringIO("1\n"), stdout)

    assert response == "1"
    assert "Confirm welding choices" in stdout.getvalue()
    assert "请输入选项编号或 field=value" in stdout.getvalue()
