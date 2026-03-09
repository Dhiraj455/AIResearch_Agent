import json, os
from pathlib import Path
from src.schemes import RunState
from src.config import settings

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