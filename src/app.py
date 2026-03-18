from datetime import datetime
from pathlib import Path
import json
import time

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


@app.post("/run")
def run(req: RunRequest):
    """Run research and automatically create a linked chat for follow-ups. Data is cached for 24 hours."""
    run_id = new_run_id()
    state = RunState(run_id=run_id, prompt=req.prompt)

    result = graph.invoke(state)
    out = RunState(**result) if isinstance(result, dict) else result
    save_state(out)

    if out.final_report_md:
        save_report(run_id, out.final_report_md)
        save_report_pdf(run_id, out.final_report_md)

    chat_id = new_run_id()
    report_content = out.final_report_md or out.draft_report_md or "(No report generated)"
    title = (req.prompt[:60] + "…") if len(req.prompt) > 60 else req.prompt
    chat = Chat(
        id=chat_id,
        title=title,
        messages=[
            Message(role="user", content=req.prompt),
            Message(role="assistant", content=report_content, run_id=run_id),
        ],
        last_run_id=run_id,
    )
    save_chat(chat)
    save_run_chat_mapping(run_id, chat_id)

    return {
        "run_id": run_id,
        "chat_id": chat_id,
        "status": "completed",
        "events": len(out.events),
    }


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
        run_id = new_run_id()
        state = RunState(run_id=run_id, prompt=req.content)
        result = graph.invoke(state)
        out = RunState(**result) if isinstance(result, dict) else result
        save_state(out)
        if out.final_report_md:
            save_report(run_id, out.final_report_md)
            save_report_pdf(run_id, out.final_report_md)
        assistant_content = out.final_report_md or out.draft_report_md or "(No report generated)"
        chat.messages.append(Message(role="assistant", content=assistant_content, run_id=run_id))
        chat.last_run_id = run_id
        if not chat.title:
            chat.title = (req.content[:60] + "…") if len(req.content) > 60 else req.content
    else:
        answer = answer_followup(req.content, chat.last_run_id)
        chat.messages.append(Message(role="assistant", content=answer))

    save_chat(chat)
    last_msg = chat.messages[-1]
    return {"message": {"role": last_msg.role, "content": last_msg.content, "run_id": last_msg.run_id}}
