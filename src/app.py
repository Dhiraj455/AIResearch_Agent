from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel
import json, time
from src.schemes import RunState
from src.agent.graph import build_graph
from src.agent.utils import new_run_id
from src.storage import save_state, load_state, save_report

app = FastAPI(title="AI Research Agent")

graph = build_graph()

class RunRequest(BaseModel):
    prompt: str

@app.post("/run")
def run(req: RunRequest):
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

    return {"run_id": run_id, "status": "completed", "events": len(out.events)}

@app.get("/runs/{run_id}")
def get_run(run_id: str):
    try:
        state = load_state(run_id)
        return state.model_dump()
    except Exception:
        raise HTTPException(status_code=404, detail="Run not found")

@app.get("/runs/{run_id}/report", response_class=PlainTextResponse)
def get_report(run_id: str):
    state = load_state(run_id)
    if not state.final_report_md:
        raise HTTPException(status_code=404, detail="Report not found")
    return state.final_report_md

@app.get("/runs/{run_id}/stream")
def stream_events(run_id: str):
    # For now, stream already-saved events; later stream live events during run execution.
    state = load_state(run_id)

    def event_gen():
        for ev in state.events:
            yield f"data: {json.dumps(ev)}\n\n"
            time.sleep(0.01)

    return StreamingResponse(event_gen(), media_type="text/event-stream")