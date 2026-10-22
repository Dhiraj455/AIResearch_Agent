from datetime import datetime
import json
import queue
import threading
import time
from typing import Callable, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel

from src.schemes import RunState, Chat, Message
from src.agent.graph import build_graph
from src.agent.utils import new_run_id
from src.config import settings
from src.storage import (
    save_state,
    load_state,
    save_report,
    save_report_pdf,
    get_cached_pdf,
    save_chat,
    load_chat,
    list_chats,
    save_run_chat_mapping,
    get_chat_for_run,
)
from src.chat_service import answer_followup
from src.cache import kv
from src.agent import cancel, live

app = FastAPI(title="AI Research Agent")

_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

graph = build_graph()


# --- Run API ---

class RunRequest(BaseModel):
    prompt: str


def _title(prompt: str) -> str:
    return (prompt[:60] + "…") if len(prompt) > 60 else prompt


def _execute_research(
    prompt: str,
    on_event: Optional[Callable[[dict], None]] = None,
    run_id: Optional[str] = None,
) -> RunState:
    """
    Run the research graph, forwarding each new event as soon as its node finishes, then persist.
    Raises cancel.RunCancelled if POST /runs/{run_id}/cancel was called (nothing is saved then).
    """
    state = RunState(run_id=run_id or new_run_id(), prompt=prompt)
    started = time.time()
    out = state
    if on_event:
        live.subscribe(state.run_id, on_event)  # nodes publish each event as it happens
    try:
        for value in graph.stream(state, stream_mode="values"):
            out = RunState.model_validate(value) if isinstance(value, dict) else value
            cancel.raise_if_cancelled(state.run_id)
    finally:
        live.unsubscribe(state.run_id)
        cancel.clear(state.run_id)
    out.stats["total_s"] = round(time.time() - started, 2)
    out.stats["cache_backend"] = kv.backend
    save_state(out)
    if out.final_report_md:
        save_report(out.run_id, out.final_report_md)
        save_report_pdf(out.run_id, out.final_report_md)
    return out


def _report_content(out: RunState) -> str:
    return out.final_report_md or out.draft_report_md or "(No report generated)"


def _create_chat_for_run(prompt: str, out: RunState) -> Chat:
    chat = Chat(
        id=new_run_id(),
        title=_title(prompt),
        messages=[
            Message(role="user", content=prompt),
            Message(role="assistant", content=_report_content(out), run_id=out.run_id),
        ],
        last_run_id=out.run_id,
    )
    save_chat(chat)
    save_run_chat_mapping(out.run_id, chat.id)
    return chat


@app.post("/run")
def run(req: RunRequest):
    """Run research and automatically create a linked chat for follow-ups. Data is cached for 24 hours."""
    out = _execute_research(req.prompt)
    chat = _create_chat_for_run(req.prompt, out)
    return {
        "run_id": out.run_id,
        "chat_id": chat.id,
        "status": "completed",
        "events": len(out.events),
    }


@app.post("/run/stream")
def run_stream(req: RunRequest):
    """
    Same as /run, but streams pipeline events live over SSE as they happen.
    Starts with `run_started` ({run_id}, used for POST /runs/{run_id}/cancel) and ends with
    `done` ({run_id, chat_id}), `cancelled`, or `error`.
    The run keeps going (and is saved) if the client merely disconnects.
    """
    events: "queue.Queue[Optional[dict]]" = queue.Queue()
    run_id = new_run_id()
    events.put({"type": "run_started", "payload": {"run_id": run_id}})

    def worker():
        try:
            out = _execute_research(req.prompt, on_event=events.put, run_id=run_id)
            chat = _create_chat_for_run(req.prompt, out)
            events.put({"type": "done", "payload": {"run_id": out.run_id, "chat_id": chat.id, "stats": out.stats}})
        except cancel.RunCancelled:
            events.put({"type": "cancelled", "payload": {"run_id": run_id}})
        except Exception as e:
            events.put({"type": "error", "payload": {"detail": str(e)}})
        finally:
            events.put(None)

    threading.Thread(target=worker, daemon=True).start()

    def event_gen():
        while True:
            try:
                ev = events.get(timeout=15)
            except queue.Empty:
                yield ": keepalive\n\n"  # keep proxies from closing an idle connection
                continue
            if ev is None:
                return
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    try:
        state = load_state(run_id)
        data = state.model_dump()
        chat_id = get_chat_for_run(run_id)
        if chat_id:
            data["chat_id"] = chat_id
        return data
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found or expired")


@app.post("/runs/{run_id}/cancel")
def cancel_run(run_id: str):
    """Ask a running research run to stop; it stops after the current LLM calls finish."""
    cancel.request_cancel(run_id)
    return {"run_id": run_id, "status": "cancelling"}


@app.get("/runs/{run_id}/events")
def get_run_events(run_id: str):
    """The run's step timeline and stats (without the heavy documents/evidence payload)."""
    try:
        state = load_state(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found or expired")
    return {"events": state.events, "stats": state.stats}


@app.get("/runs/{run_id}/report", response_class=PlainTextResponse)
def get_report(run_id: str):
    try:
        state = load_state(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found or expired")
    if not state.final_report_md:
        raise HTTPException(status_code=404, detail="Report not found")
    return state.final_report_md


@app.get("/runs/{run_id}/report.pdf")
def get_report_pdf(run_id: str):
    """Download the research report as PDF. Cached for 24 hours."""
    pdf_bytes = get_cached_pdf(run_id)
    if pdf_bytes is None:
        try:
            state = load_state(run_id)
            if state.final_report_md:
                save_report_pdf(run_id, state.final_report_md)
                pdf_bytes = get_cached_pdf(run_id)
        except FileNotFoundError:
            pass
    if pdf_bytes is None:
        raise HTTPException(status_code=404, detail="PDF report not found or expired")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="research_report_{run_id}.pdf"',
        },
    )


@app.get("/runs/{run_id}/stream")
def stream_events(run_id: str):
    try:
        state = load_state(run_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Run not found or expired")

    def event_gen():
        for ev in state.events:
            yield f"data: {json.dumps(ev)}\n\n"
            time.sleep(0.01)

    return StreamingResponse(event_gen(), media_type="text/event-stream")


# --- Chat API ---

class CreateChatResponse(BaseModel):
    chat_id: str


class SendMessageRequest(BaseModel):
    content: str
    research: bool = False


@app.post("/chats", response_model=CreateChatResponse)
def create_chat():
    """Create a new empty chat. Cached for 24 hours."""
    chat_id = new_run_id()
    chat = Chat(id=chat_id)
    save_chat(chat)
    return CreateChatResponse(chat_id=chat_id)


@app.get("/chats")
def get_chats():
    """List all chats (most recently updated first). Only non-expired chats are returned."""
    chats = list_chats()
    return [
        {
            "id": c.id,
            "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
            "message_count": len(c.messages),
        }
        for c in chats
    ]


@app.get("/chats/{chat_id}")
def get_chat(chat_id: str):
    """Get a chat with all messages."""
    try:
        chat = load_chat(chat_id)
        return chat.model_dump(mode="json")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Chat not found or expired")


@app.post("/chats/{chat_id}/messages")
def send_message(chat_id: str, req: SendMessageRequest):
    """
    Send a user message. First message or research=True runs full research;
    otherwise answers using prior report (follow-up). Data is cached for 24 hours.
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Chat not found or expired")

    chat.messages.append(Message(role="user", content=req.content))
    chat.updated_at = datetime.utcnow()

    is_first_message = len(chat.messages) == 1
    do_research = req.research or is_first_message or not chat.last_run_id

    if do_research:
        out = _execute_research(req.content)
        chat.messages.append(Message(role="assistant", content=_report_content(out), run_id=out.run_id))
        chat.last_run_id = out.run_id
        save_run_chat_mapping(out.run_id, chat.id)
        if not chat.title:
            chat.title = _title(req.content)
    else:
        answer = answer_followup(req.content, chat.last_run_id)
        chat.messages.append(Message(role="assistant", content=answer))

    save_chat(chat)
    last_msg = chat.messages[-1]
    return {"message": {"role": last_msg.role, "content": last_msg.content, "run_id": last_msg.run_id}}
