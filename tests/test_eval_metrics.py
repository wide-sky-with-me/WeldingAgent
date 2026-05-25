from pwps_agent.core.eval_metrics import compute_agent_metrics
from pwps_agent.core.state import create_initial_state


def test_metrics_count_override_and_field_statuses():
    state = create_initial_state("Q355B GMAW", "auto_draft")
    state.fields["base_material"].status = "filled"
    state.fields["shielding_gas"].status = "candidate"
    state.trace.append(
        {
            "event_type": "agent_action_overridden",
            "payload": {"reason_code": "completed_action"},
        }
    )

    metrics = compute_agent_metrics(state)

    assert metrics["field_status_counts"]["filled"] == 1
    assert metrics["field_status_counts"]["candidate"] == 1
    assert metrics["override_count"] == 1
    assert metrics["override_reason_counts"]["completed_action"] == 1
