from pathlib import Path

from pwps_agent.cli import build_parser, main


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


def test_cli_reports_runtime_failure_without_traceback(monkeypatch, capsys) -> None:
    def failing_run_auto_draft(*args, **kwargs):
        raise RuntimeError("provider timeout")

    monkeypatch.setattr("pwps_agent.cli.run_auto_draft", failing_run_auto_draft)

    exit_code = main(["auto-draft", "Q355B 12mm GMAW pWPS"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "provider timeout" in captured.err
    assert "Traceback" not in captured.err
