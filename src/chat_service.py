"""Chat service: follow-up answers using research report context."""

import json

from src.agent.prompt import FOLLOWUP_PROMPT
from src.agent.utils import llm_text
from src.storage import load_state


def answer_followup(question: str, run_id: str) -> str:
    """
    Answer a follow-up question using the report and evidence from a previous research run.
    Limits evidence to top 25 items to keep context small for faster response.
    """
    state = load_state(run_id)
    report_md = state.final_report_md or state.draft_report_md or ""
    # Limit evidence to reduce tokens and speed up follow-up
    evidence_json = json.dumps(
        [{"snippet": e.snippet, "url": e.url} for e in state.evidence[:25]],
        indent=2,
    )
    return llm_text(
        FOLLOWUP_PROMPT.format(
            report_md=report_md,
            evidence_json=evidence_json,
            question=question,
        ),
        fast=True,
    )
