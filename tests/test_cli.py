from pathlib import Path

from pwps_agent.cli import build_parser, main
from pwps_agent.core.state import create_initial_state
from pwps_agent.graph.checkpoints import save_checkpoint
from pwps_agent.workflows.auto_draft import AutoDraftResult


def _fill_minimum_core_fields(state) -> None:
    for field_id, value in {
        "applicable_standard": "AWS D1.1",
        "base_material": "Q355B",
        "thickness": "12mm",
        "workpiece_type": "plate",
        "welding_process": "GMAW",
        "joint_type": "butt joint",
        "welding_position": "flat",
    }.items():
        state.fields[field_id].value = value
        state.fields[field_id].status = "filled"


def test_cli_parser_accepts_auto_draft_requirement_and_output_dir(tmp_path: Path) -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "auto-draft",
            "Q355B 12mm GMAW pWPS",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert args.command == "auto-draft"
    assert args.requirement == "Q355B 12mm GMAW pWPS"
    assert args.output_dir == tmp_path


def test_cli_parser_accepts_guided_draft_requirement_and_output_dir(tmp_path: Path) -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "guided-draft",
            "Q355B 12mm GMAW pWPS",
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "guided_cli",
        ]
    )

    assert args.command == "guided-draft"
    assert args.requirement == "Q355B 12mm GMAW pWPS"
    assert args.output_dir == tmp_path
    assert args.run_id == "guided_cli"


def test_cli_parser_accepts_guided_confirmation_commands(tmp_path: Path) -> None:
    parser = build_parser()
    state_path = tmp_path / "pwps.json"

    confirm_args = parser.parse_args(
        [
            "guided-confirm",
            str(state_path),
            "--set",
            "filler_material=ER50-6",
            "--message",
            "Confirm filler.",
        ]
    )
    web_args = parser.parse_args(
        [
            "guided-confirm-web",
            str(state_path),
            "--host",
            "127.0.0.1",
            "--port",
            "9876",
        ]
    )

    assert confirm_args.command == "guided-confirm"
    assert confirm_args.set_values == ["filler_material=ER50-6"]
    assert web_args.command == "guided-confirm-web"
    assert web_args.port == 9876


def test_cli_parser_accepts_guided_confirmation_view_and_resume(tmp_path: Path) -> None:
    parser = build_parser()
    state_path = tmp_path / "pwps.json"

    view_args = parser.parse_args(["guided-confirm-view", str(state_path)])
    resume_args = parser.parse_args(
        [
            "guided-confirm-resume",
            str(state_path),
            "--set",
            "filler_material=ER50-6",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert view_args.command == "guided-confirm-view"
    assert resume_args.command == "guided-confirm-resume"
    assert resume_args.output_dir == tmp_path


def test_cli_parser_accepts_guided_confirmation_resume_run(tmp_path: Path) -> None:
    parser = build_parser()

    args = parser.parse_args(
        [
            "guided-confirm-resume-run",
            "guided_run",
            "--set",
            "filler_material=ER50-6",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert args.command == "guided-confirm-resume-run"
    assert args.run_id == "guided_run"
    assert args.output_dir == tmp_path


def test_cli_parser_accepts_supplement_commands(tmp_path: Path) -> None:
    parser = build_parser()
    state_path = tmp_path / "pwps.json"

    state_args = parser.parse_args(
        [
            "supplement-state",
            str(state_path),
            "--message",
            "Base material is Q355B.",
            "--set",
            "base_material=Q355B",
            "--output-dir",
            str(tmp_path),
        ]
    )
    run_args = parser.parse_args(
        [
            "supplement-run",
            "supplement_run",
            "--message",
            "Base material is Q355B.",
            "--set",
            "base_material=Q355B",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert state_args.command == "supplement-state"
    assert state_args.state_path == state_path
    assert run_args.command == "supplement-run"
    assert run_args.run_id == "supplement_run"


def test_cli_guided_confirmation_resume_writes_artifacts(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "state.json"
    state = create_initial_state("Q355B 12mm GMAW", "guided_confirmation", run_id="cli_resume")
    state.status = "need_user_input"
    _fill_minimum_core_fields(state)
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

    exit_code = main(
        [
            "guided-confirm-resume",
            str(state_path),
            "--set",
            "filler_material=ER50-6",
            "--message",
            "Confirm filler.",
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(tmp_path / "cli_resume") in captured.out
    assert (tmp_path / "cli_resume" / "pwps_draft.md").exists()


def test_cli_guided_confirmation_resume_run_loads_checkpoint(tmp_path: Path, capsys) -> None:
    state = create_initial_state("Q355B 12mm GMAW", "guided_confirmation", run_id="cli_resume_run")
    state.status = "need_user_input"
    _fill_minimum_core_fields(state)
    state.fields["filler_material"].value = "ER50-6"
    state.fields["filler_material"].status = "candidate"
    save_checkpoint(state, tmp_path, "ask_user")

    exit_code = main(
        [
            "guided-confirm-resume-run",
            "cli_resume_run",
            "--set",
            "filler_material=ER50-6",
            "--message",
            "Confirm filler from checkpoint.",
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(tmp_path / "cli_resume_run") in captured.out
    assert (tmp_path / "cli_resume_run" / "pwps_draft.md").exists()


def test_cli_supplement_state_updates_saved_state_and_artifacts(tmp_path: Path, capsys) -> None:
    state_path = tmp_path / "state.json"
    state = create_initial_state("Generate pWPS draft.", "auto_draft", run_id="cli_supplement_state")
    state.status = "done"
    state_path.write_text(state.model_dump_json(indent=2), encoding="utf-8")

    exit_code = main(
        [
            "supplement-state",
            str(state_path),
            "--message",
            "Base material is Q355B.",
            "--set",
            "base_material=Q355B",
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(tmp_path / "cli_supplement_state") in captured.out
    assert (tmp_path / "cli_supplement_state" / "pwps_draft.md").exists()
    assert "Q355B" in state_path.read_text(encoding="utf-8")


def test_cli_supplement_run_loads_checkpoint(tmp_path: Path, capsys) -> None:
    state = create_initial_state("Generate pWPS draft.", "auto_draft", run_id="cli_supplement_run")
    state.status = "done"
    save_checkpoint(state, tmp_path, "finish")

    exit_code = main(
        [
            "supplement-run",
            "cli_supplement_run",
            "--message",
            "Base material is Q355B.",
            "--set",
            "base_material=Q355B",
            "--output-dir",
            str(tmp_path),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(tmp_path / "cli_supplement_run") in captured.out
    assert (tmp_path / "cli_supplement_run" / "pwps.json").exists()


def test_cli_auto_draft_uses_graph_runtime_by_default(monkeypatch, tmp_path: Path, capsys) -> None:
    calls = {}

    def fake_run_graph_auto_draft(requirement, settings, run_id):
        calls["requirement"] = requirement
        calls["output_dir"] = settings.paths.output_dir
        calls["run_id"] = run_id
        state = create_initial_state(requirement, "auto_draft", run_id=run_id)
        return AutoDraftResult(state=state, output_dir=str(tmp_path / run_id))

    monkeypatch.setattr("pwps_agent.cli.run_graph_auto_draft", fake_run_graph_auto_draft, raising=False)

    exit_code = main(
        [
            "auto-draft",
            "Q355B 12mm GMAW pWPS",
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "cli_graph_default",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(tmp_path / "cli_graph_default") in captured.out
    assert calls == {
        "requirement": "Q355B 12mm GMAW pWPS",
        "output_dir": tmp_path,
        "run_id": "cli_graph_default",
    }


def test_cli_auto_draft_emits_progress_logs(monkeypatch, tmp_path: Path, capsys) -> None:
    def fake_run_graph_auto_draft(requirement, settings, run_id):
        state = create_initial_state(requirement, "auto_draft", run_id=run_id)
        return AutoDraftResult(state=state, output_dir=str(tmp_path / run_id))

    monkeypatch.setattr("pwps_agent.cli.run_graph_auto_draft", fake_run_graph_auto_draft, raising=False)

    exit_code = main(
        [
            "auto-draft",
            "Q355B 12mm GMAW pWPS",
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "cli_logs",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Starting auto-draft run_id=cli_logs" in captured.err
    assert "Completed auto-draft run_id=cli_logs" in captured.err


def test_cli_guided_draft_uses_guided_workflow(monkeypatch, tmp_path: Path, capsys) -> None:
    calls = {}

    def fake_run_graph_guided_draft(requirement, settings, run_id):
        calls["requirement"] = requirement
        calls["output_dir"] = settings.paths.output_dir
        calls["run_id"] = run_id
        state = create_initial_state(requirement, "guided_confirmation", run_id=run_id)
        state.status = "need_user_input"
        return AutoDraftResult(state=state, output_dir=str(tmp_path / run_id))

    monkeypatch.setattr("pwps_agent.cli.run_graph_guided_draft", fake_run_graph_guided_draft, raising=False)

    exit_code = main(
        [
            "guided-draft",
            "Q355B 12mm GMAW pWPS",
            "--output-dir",
            str(tmp_path),
            "--run-id",
            "guided_cli",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert str(tmp_path / "guided_cli") in captured.out
    assert "Completed guided-draft run_id=guided_cli status=need_user_input" in captured.err
    assert calls == {
        "requirement": "Q355B 12mm GMAW pWPS",
        "output_dir": tmp_path,
        "run_id": "guided_cli",
    }


def test_cli_reports_runtime_failure_without_traceback(monkeypatch, capsys) -> None:
    def failing_run_graph_auto_draft(*args, **kwargs):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr("pwps_agent.cli.run_graph_auto_draft", failing_run_graph_auto_draft, raising=False)

    exit_code = main(["auto-draft", "Q355B 12mm GMAW pWPS"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "provider timeout" in captured.err
    assert "Traceback" not in captured.err
