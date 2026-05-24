from pwps_agent.config import LLMSettings
from pwps_agent.core.state import create_initial_state
from pwps_agent.llm.openai_compatible import OpenAICompatibleClient
from pwps_agent.tools.requirement_understanding import understand_requirement


class StaticLLMTransport:
    def post_json(self, url: str, payload: dict, headers: dict[str, str], timeout: int) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": """
                        {
                          "core_fields": {
                            "applicable_standard": "AWS D1.1",
                            "base_material": "Q355B",
                            "thickness": "12mm",
                            "workpiece_type": "plate",
                            "welding_process": "GMAW",
                            "joint_type": "butt joint",
                            "welding_position": "flat"
                          },
                          "missing_core_fields": []
                        }
                        """
                    }
                }
            ]
        }


def test_requirement_understanding_updates_core_fields_and_field_state() -> None:
    state = create_initial_state(
        user_input="请生成 Q355B 12mm 板材 GMAW 对接 平焊 AWS D1.1 pWPS 草案",
        interaction_mode="auto_draft",
    )
    client = OpenAICompatibleClient(
        LLMSettings(api_key="key", base_url="https://llm.example/v1", model="model"),
        transport=StaticLLMTransport(),
    )

    result = understand_requirement(state, client)

    assert result.success is True
    patch = result.state_patch
    assert patch["core_fields"]["base_material"] == "Q355B"
    assert patch["fields"]["base_material"]["value"] == "Q355B"
    assert patch["fields"]["base_material"]["status"] == "filled"
    assert "applicable_standard" in patch["fields"]


class PartialLLMTransport:
    def post_json(self, url: str, payload: dict, headers: dict[str, str], timeout: int) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "content": """
                        {
                          "core_fields": {
                            "thickness": "12 mm",
                            "welding_process": "GMAW",
                            "joint_type": "butt joint",
                            "welding_position": "flat"
                          },
                          "missing_core_fields": ["base_material", "applicable_standard", "workpiece_type"]
                        }
                        """
                    }
                }
            ]
        }


def test_requirement_understanding_normalizes_obvious_fields_missed_by_llm() -> None:
    state = create_initial_state(
        user_input="请生成 Q355B，12mm 板材，GMAW，对接接头，平焊，按 AWS D1.1 的 pWPS 草案",
        interaction_mode="auto_draft",
    )
    client = OpenAICompatibleClient(
        LLMSettings(api_key="key", base_url="https://llm.example/v1", model="model"),
        transport=PartialLLMTransport(),
    )

    result = understand_requirement(state, client)

    core_fields = result.state_patch["core_fields"]
    assert core_fields["base_material"] == "Q355B"
    assert core_fields["applicable_standard"] == "AWS D1.1"
    assert core_fields["workpiece_type"] == "plate"
    assert core_fields["thickness"] == "12 mm"
    assert core_fields["welding_process"] == "GMAW"
    assert core_fields["joint_type"] == "butt joint"
    assert core_fields["welding_position"] == "flat"
    assert result.state_patch["fields"]["base_material"]["status"] == "filled"
