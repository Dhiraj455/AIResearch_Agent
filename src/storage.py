import io
import json
import os
from pathlib import Path

import markdown
from xhtml2pdf import pisa

from src.schemes import RunState, Chat
from src.config import settings


# --- Chat storage ---

def chats_dir(user_id: str) -> Path:
    p = Path(settings.CHATS_DIR) / user_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def chat_path(chat_id: str, user_id: str) -> Path:
    return chats_dir(user_id) / f"chat_{chat_id}.json"


def save_chat(chat: Chat, user_id: str) -> None:
    chat_path(chat.id, user_id).write_text(chat.model_dump_json(indent=2), encoding="utf-8")


def load_chat(chat_id: str, user_id: str) -> Chat:
    p = chat_path(chat_id, user_id)
    if not p.exists():
        raise FileNotFoundError(f"Chat {chat_id} not found")
    return Chat.model_validate_json(p.read_text(encoding="utf-8"))


def list_chats(user_id: str) -> list[Chat]:
    """List all chats for a user, sorted by updated_at descending."""
    chats = []
    for f in chats_dir(user_id).glob("chat_*.json"):
        try:
            chats.append(Chat.model_validate_json(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    chats.sort(key=lambda c: c.updated_at, reverse=True)
    return chats


def _run_chat_index_path(user_id: str) -> Path:
    return chats_dir(user_id) / "_run_to_chat.json"


def save_run_chat_mapping(run_id: str, chat_id: str, user_id: str) -> None:
    """Record which chat was created for a run (POST /run flow)."""
    p = _run_chat_index_path(user_id)
    index = {}
    if p.exists():
        try:
            index = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    index[run_id] = chat_id
    p.write_text(json.dumps(index, indent=2), encoding="utf-8")


def get_chat_for_run(run_id: str, user_id: str) -> str | None:
    """Get chat_id for a run created via POST /run."""
    p = _run_chat_index_path(user_id)
    if not p.exists():
        return None
    index = json.loads(p.read_text(encoding="utf-8"))
    return index.get(run_id)


# --- Run storage ---

def runs_dir(user_id: str) -> Path:
    p = Path(settings.RUNS_DIR) / user_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def run_path(run_id: str, user_id: str) -> Path:
    return runs_dir(user_id) / f"run_{run_id}.json"


def save_state(state: RunState, user_id: str) -> None:
    p = run_path(state.run_id, user_id)
    p.write_text(state.model_dump_json(indent=2), encoding="utf-8")


def load_state(run_id: str, user_id: str) -> RunState:
    p = run_path(run_id, user_id)
    return RunState.model_validate_json(p.read_text(encoding="utf-8"))


def save_report(run_id: str, report_md: str, user_id: str) -> str:
    rp = runs_dir(user_id) / f"report_{run_id}.md"
    rp.write_text(report_md, encoding="utf-8")
    return str(rp)


def _markdown_to_pdf(report_md: str) -> bytes:
    """Convert markdown report to PDF bytes."""
    html = markdown.markdown(
        report_md,
        extensions=["extra", "sane_lists"],
    )
    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Georgia, serif; font-size: 11pt; line-height: 1.5; margin: 2cm; color: #333; }}
            h1 {{ font-size: 18pt; margin-top: 0; border-bottom: 1px solid #ccc; padding-bottom: 0.3em; }}
            h2 {{ font-size: 14pt; margin-top: 1.2em; }}
            h3 {{ font-size: 12pt; margin-top: 1em; }}
            p {{ margin: 0.5em 0; }}
            ul, ol {{ margin: 0.5em 0; padding-left: 1.5em; }}
            a {{ color: #059669; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
            .source {{ font-size: 9pt; color: #666; }}
        </style>
    </head>
    <body>{html}</body>
    </html>
    """
    out = io.BytesIO()
    pisa_status = pisa.CreatePDF(styled_html, dest=out, encoding="utf-8")
    if pisa_status.err:
        raise RuntimeError(f"PDF generation failed: {pisa_status.err}")
    return out.getvalue()


def save_report_pdf(run_id: str, report_md: str, user_id: str) -> str | None:
    """Generate and save PDF from markdown report. Returns path or None on failure."""
    try:
        pdf_bytes = _markdown_to_pdf(report_md)
        pdf_path = runs_dir(user_id) / f"report_{run_id}.pdf"
        pdf_path.write_bytes(pdf_bytes)
        return str(pdf_path)
    except Exception:
        return None