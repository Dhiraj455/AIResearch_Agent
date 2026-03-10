import json, os
from pathlib import Path
from src.schemes import RunState, Chat
from src.config import settings


# --- Chat storage ---

def chats_dir() -> Path:
    p = Path(settings.CHATS_DIR)
    p.mkdir(parents=True, exist_ok=True)
    return p


def chat_path(chat_id: str) -> Path:
    return chats_dir() / f"chat_{chat_id}.json"


def save_chat(chat: Chat) -> None:
    chat_path(chat.id).write_text(chat.model_dump_json(indent=2), encoding="utf-8")


def load_chat(chat_id: str) -> Chat:
    p = chat_path(chat_id)
    if not p.exists():
        raise FileNotFoundError(f"Chat {chat_id} not found")
    return Chat.model_validate_json(p.read_text(encoding="utf-8"))


def list_chats() -> list[Chat]:
    """List all chats, sorted by updated_at descending."""
    chats = []
    for f in chats_dir().glob("chat_*.json"):
        try:
            chats.append(Chat.model_validate_json(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    chats.sort(key=lambda c: c.updated_at, reverse=True)
    return chats


def _run_chat_index_path() -> Path:
    return chats_dir() / "_run_to_chat.json"


def save_run_chat_mapping(run_id: str, chat_id: str) -> None:
    """Record which chat was created for a run (POST /run flow)."""
    p = _run_chat_index_path()
    index = {}
    if p.exists():
        try:
            index = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    index[run_id] = chat_id
    p.write_text(json.dumps(index, indent=2), encoding="utf-8")


def get_chat_for_run(run_id: str) -> str | None:
    """Get chat_id for a run created via POST /run."""
    p = _run_chat_index_path()
    if not p.exists():
        return None
    index = json.loads(p.read_text(encoding="utf-8"))
    return index.get(run_id)


# --- Run storage ---

def run_path(run_id: str) -> Path:
    Path(settings.RUNS_DIR).mkdir(parents=True, exist_ok=True)
    return Path(settings.RUNS_DIR) / f"run_{run_id}.json"

def save_state(state: RunState) -> None:
    p = run_path(state.run_id)
    p.write_text(state.model_dump_json(indent=2), encoding="utf-8")

def load_state(run_id: str) -> RunState:
    p = run_path(run_id)
    return RunState.model_validate_json(p.read_text(encoding="utf-8"))

def save_report(run_id: str, report_md: str) -> str:
    Path(settings.RUNS_DIR).mkdir(parents=True, exist_ok=True)
    rp = Path(settings.RUNS_DIR) / f"report_{run_id}.md"
    rp.write_text(report_md, encoding="utf-8")
    return str(rp)