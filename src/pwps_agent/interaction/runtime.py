from __future__ import annotations

import sys
from typing import Callable, TextIO

from pwps_agent.config import Settings
from pwps_agent.core.state import PWPSState
from pwps_agent.interaction.normalizer import normalize_interaction_response
from pwps_agent.interaction.terminal import collect_terminal_response
from pwps_agent.workflows.auto_draft import AutoDraftResult
from pwps_agent.workflows.interaction_resume import resume_interaction

TerminalCollector = Callable[[dict, TextIO, TextIO], str]


def continue_interactive_run(
    result: AutoDraftResult,
    settings: Settings,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    collector: TerminalCollector | None = None,
) -> AutoDraftResult:
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    collector = collector or collect_terminal_response

    if not should_prompt_inline(result.state, stdin=stdin):
        return result

    current = result
    while should_prompt_inline(current.state, stdin=stdin):
        interaction = current.state.pending_interaction or {}
        raw_text = collector(interaction, stdin, stdout)
        payload = normalize_interaction_response(interaction, raw_text)
        resumed = resume_interaction(current.state, payload, settings=settings)
        current = AutoDraftResult(state=resumed.state, output_dir=resumed.output_dir)
    return current


def should_prompt_inline(state: PWPSState, stdin: TextIO | None = None) -> bool:
    stdin = stdin or sys.stdin
    isatty = getattr(stdin, "isatty", None)
    return (
        state.status == "need_user_input"
        and bool(state.pending_interaction)
        and callable(isatty)
        and bool(isatty())
    )
