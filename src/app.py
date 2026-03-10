from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field
import json, time

from src.schemes import RunState, Chat, Message
from src.agent.graph import build_graph
from src.agent.utils import new_run_id
from src.config import settings
from src.storage import save_state, load_state, save_report, save_report_pdf, save_chat, load_chat, list_chats, save_run_chat_mapping, get_chat_for_run
from src.chat_service import answer_followup

app = FastAPI(title="AI Research Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

graph = build_graph()

# --- Run API (legacy) ---

class RunRequest(BaseModel):
    prompt: str

@app.post("/run")
def run(req: RunRequest):
    """Run research and automatically create a linked chat for follow-ups."""
    run_id = new_run_id()
    state = RunState(run_id=run_id, prompt=req.prompt)

    # execute graph
    # NOTE: for long runs, you'll later move this to Celery/RQ
    result = graph.invoke(state)
    # LangGraph returns a dict-like object, convert back to RunState
    out = RunState(**result) if isinstance(result, dict) else result
    save_state(out)

    if out.final_report_md:
        save_report(run_id, out.final_report_md)
        save_report_pdf(run_id, out.final_report_md)

    # Create linked chat so user can follow up immediately
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
    except Exception:
        raise HTTPException(status_code=404, detail="Run not found")

@app.get("/runs/{run_id}/report", response_class=PlainTextResponse)
def get_report(run_id: str):
    state = load_state(run_id)
    if not state.final_report_md:
        raise HTTPException(status_code=404, detail="Report not found")
    return state.final_report_md


@app.get("/runs/{run_id}/report.pdf")
def get_report_pdf(run_id: str):
    """Download the research report as PDF."""
    from pathlib import Path
    pdf_path = Path(settings.RUNS_DIR) / f"report_{run_id}.pdf"
    if not pdf_path.exists():
        # Try to generate if we have the markdown
        try:
            state = load_state(run_id)
            if state.final_report_md:
                path_str = save_report_pdf(run_id, state.final_report_md)
                if path_str:
                    pdf_path = Path(path_str)
        except Exception:
            pass
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF report not found")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=f"research_report_{run_id}.pdf",
        headers={"Content-Disposition": f'attachment; filename="research_report_{run_id}.pdf"'},
    )


@app.get("/runs/{run_id}/stream")
def stream_events(run_id: str):
    # For now, stream already-saved events; later stream live events during run execution.
    state = load_state(run_id)

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
    research: bool = False  # True = run new research; False = follow-up using prior report


@app.post("/chats", response_model=CreateChatResponse)
def create_chat():
    """Create a new empty chat."""
    chat_id = new_run_id()
    chat = Chat(id=chat_id)
    save_chat(chat)
    return CreateChatResponse(chat_id=chat_id)


@app.get("/chats")
def get_chats():
    """List all chats, most recently updated first."""
    chats = list_chats()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at.isoformat(), "updated_at": c.updated_at.isoformat(), "message_count": len(c.messages)} for c in chats]


@app.get("/chats/{chat_id}")
def get_chat(chat_id: str):
    """Get a chat with all messages."""
    try:
        chat = load_chat(chat_id)
        return chat.model_dump(mode="json")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Chat not found")


@app.post("/chats/{chat_id}/messages")
def send_message(chat_id: str, req: SendMessageRequest):
    """
    Send a user message. First message or research=True runs full research;
    otherwise answers using prior report (follow-up).
    """
    try:
        chat = load_chat(chat_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Chat not found")

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