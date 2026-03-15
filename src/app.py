from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel
import json, time

from src.schemes import RunState, Chat, Message
from src.agent.graph import build_graph
from src.agent.utils import new_run_id
from src.config import settings
from src.storage import (
    save_state, load_state, save_report, save_report_pdf, runs_dir,
    save_chat, load_chat, list_chats, save_run_chat_mapping, get_chat_for_run,
)
from src.chat_service import answer_followup
from src.auth import get_current_user, authenticate_user, create_access_token
from src.user_storage import register_user

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

UserDep = Annotated[dict, Depends(get_current_user)]


# --- Auth API ---

class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@app.post("/auth/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    """Register a new user and return an access token."""
    if not req.email or not req.email.strip():
        raise HTTPException(status_code=400, detail="Email is required")
    if not req.password or len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    try:
        user = register_user(req.email.strip(), req.password)
        token = create_access_token(user["id"], user["email"])
        return TokenResponse(access_token=token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/auth/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """Authenticate and return an access token."""
    user = authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], user["email"])
    return TokenResponse(access_token=token)


@app.get("/auth/me")
def me(user: UserDep):
    """Return current user info (requires valid token)."""
    return {"id": user["id"], "email": user["email"]}


# --- Run API ---

class RunRequest(BaseModel):
    prompt: str


@app.post("/run")
def run(req: RunRequest, user: UserDep):
    """Run research and automatically create a linked chat for follow-ups."""
    user_id = user["id"]
    run_id = new_run_id()
    state = RunState(run_id=run_id, prompt=req.prompt)

    result = graph.invoke(state)
    out = RunState(**result) if isinstance(result, dict) else result
    save_state(out, user_id)

    if out.final_report_md:
        save_report(run_id, out.final_report_md, user_id)
        save_report_pdf(run_id, out.final_report_md, user_id)

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
    save_chat(chat, user_id)
    save_run_chat_mapping(run_id, chat_id, user_id)

    return {
        "run_id": run_id,
        "chat_id": chat_id,
        "status": "completed",
        "events": len(out.events),
    }


@app.get("/runs/{run_id}")
def get_run(run_id: str, user: UserDep):
    try:
        state = load_state(run_id, user["id"])
        data = state.model_dump()
        chat_id = get_chat_for_run(run_id, user["id"])
        if chat_id:
            data["chat_id"] = chat_id
        return data
    except Exception:
        raise HTTPException(status_code=404, detail="Run not found")


@app.get("/runs/{run_id}/report", response_class=PlainTextResponse)
def get_report(run_id: str, user: UserDep):
    state = load_state(run_id, user["id"])
    if not state.final_report_md:
        raise HTTPException(status_code=404, detail="Report not found")
    return state.final_report_md


@app.get("/runs/{run_id}/report.pdf")
def get_report_pdf(run_id: str, user: UserDep):
    """Download the research report as PDF."""
    user_id = user["id"]
    pdf_path = runs_dir(user_id) / f"report_{run_id}.pdf"
    if not pdf_path.exists():
        try:
            state = load_state(run_id, user_id)
            if state.final_report_md:
                path_str = save_report_pdf(run_id, state.final_report_md, user_id)
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
def stream_events(run_id: str, user: UserDep):
    state = load_state(run_id, user["id"])

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
def create_chat(user: UserDep):
    """Create a new empty chat."""
    chat_id = new_run_id()
    chat = Chat(id=chat_id)
    save_chat(chat, user["id"])
    return CreateChatResponse(chat_id=chat_id)


@app.get("/chats")
def get_chats(user: UserDep):
    """List all chats for the current user, most recently updated first."""
    chats = list_chats(user["id"])
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
def get_chat(chat_id: str, user: UserDep):
    """Get a chat with all messages (only if owned by current user)."""
    try:
        chat = load_chat(chat_id, user["id"])
        return chat.model_dump(mode="json")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Chat not found")


@app.post("/chats/{chat_id}/messages")
def send_message(chat_id: str, req: SendMessageRequest, user: UserDep):
    """
    Send a user message. First message or research=True runs full research;
    otherwise answers using prior report (follow-up).
    """
    user_id = user["id"]
    try:
        chat = load_chat(chat_id, user_id)
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
        save_state(out, user_id)
        if out.final_report_md:
            save_report(run_id, out.final_report_md, user_id)
            save_report_pdf(run_id, out.final_report_md, user_id)
        assistant_content = out.final_report_md or out.draft_report_md or "(No report generated)"
        chat.messages.append(Message(role="assistant", content=assistant_content, run_id=run_id))
        chat.last_run_id = run_id
        if not chat.title:
            chat.title = (req.content[:60] + "…") if len(req.content) > 60 else req.content
    else:
        answer = answer_followup(req.content, chat.last_run_id, user_id)
        chat.messages.append(Message(role="assistant", content=answer))

    save_chat(chat, user_id)
    last_msg = chat.messages[-1]
    return {"message": {"role": last_msg.role, "content": last_msg.content, "run_id": last_msg.run_id}}
