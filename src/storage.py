"""
Redis-backed cache for runs, chats, and report PDFs with TTL.

This project intentionally does not persist user data long-term.
All cached items expire after CACHE_TTL_HOURS (default 24h).
"""

from __future__ import annotations

import io
from typing import Optional

import markdown
import redis
from xhtml2pdf import pisa

from src.config import settings
from src.schemes import Chat, RunState


_TTL_S = settings.CACHE_TTL_HOURS * 3600


def _redis() -> redis.Redis:
    if not settings.REDIS_URL:
        raise RuntimeError(
            "REDIS_URL is not set. Set it in your environment or .env (e.g. redis://localhost:6379/0)."
        )
    # decode_responses=False => store bytes safely (PDF, etc.)
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)


def _k_run(run_id: str) -> str:
    return f"run:{run_id}"


def _k_chat(chat_id: str) -> str:
    return f"chat:{chat_id}"


def _k_run_chat(run_id: str) -> str:
    return f"run_chat:{run_id}"


def _k_pdf(run_id: str) -> str:
    return f"pdf:{run_id}"


# --- Run cache ---


def save_state(state: RunState) -> None:
    r = _redis()
    r.setex(_k_run(state.run_id), _TTL_S, state.model_dump_json(indent=2).encode("utf-8"))


def load_state(run_id: str) -> RunState:
    r = _redis()
    raw = r.get(_k_run(run_id))
    if not raw:
        raise FileNotFoundError(f"Run {run_id} not found or expired")
    text = raw.decode("utf-8")
    return RunState.model_validate_json(text)


def save_report(run_id: str, report_md: str) -> str:
    """
    Reports are already stored inside RunState.final_report_md / draft_report_md.
    This function is kept for API compatibility and returns the run_id.
    """
    return run_id


# --- PDF cache ---


def _markdown_to_pdf(report_md: str) -> bytes:
    html = markdown.markdown(report_md, extensions=["extra", "sane_lists"])
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


def save_report_pdf(run_id: str, report_md: str) -> str | None:
    """
    Cache PDF bytes in Redis.
    Stored as raw bytes (base64 not required).
    """
    try:
        pdf_bytes = _markdown_to_pdf(report_md)
        r = _redis()
        r.setex(_k_pdf(run_id), _TTL_S, pdf_bytes)
        return run_id
    except Exception:
        return None


def get_cached_pdf(run_id: str) -> Optional[bytes]:
    r = _redis()
    raw = r.get(_k_pdf(run_id))
    if not raw:
        return None
    return raw


# --- Chat cache ---


def save_chat(chat: Chat) -> None:
    r = _redis()
    r.setex(_k_chat(chat.id), _TTL_S, chat.model_dump_json(indent=2).encode("utf-8"))


def load_chat(chat_id: str) -> Chat:
    r = _redis()
    raw = r.get(_k_chat(chat_id))
    if not raw:
        raise FileNotFoundError(f"Chat {chat_id} not found or expired")
    return Chat.model_validate_json(raw.decode("utf-8"))


def list_chats() -> list[Chat]:
    r = _redis()
    # Note: KEYS is OK for small dev use; for scale use SCAN.
    keys = r.keys(_k_chat("*"))
    chats: list[Chat] = []
    for k in keys:
        raw = r.get(k)
        if not raw:
            continue
        try:
            chats.append(Chat.model_validate_json(raw.decode("utf-8")))
        except Exception:
            continue
    chats.sort(key=lambda c: c.updated_at, reverse=True)
    return chats


def save_run_chat_mapping(run_id: str, chat_id: str) -> None:
    r = _redis()
    # Tie mapping TTL to run TTL.
    r.setex(_k_run_chat(run_id), _TTL_S, chat_id.encode("utf-8"))


def get_chat_for_run(run_id: str) -> str | None:
    r = _redis()
    raw = r.get(_k_run_chat(run_id))
    if not raw:
        return None
    return raw.decode("utf-8")

