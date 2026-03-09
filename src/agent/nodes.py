import json
import time
from typing import Any, Dict

from src.schemes import (
    RunState,
    Plan,
    SearchResult,
    Document,
    Evidence,
    Coverage,
    VerificationIssue,
)
from src.agent.prompt import PLAN_PROMPT, EVIDENCE_PROMPT, WRITE_PROMPT, VERIFY_PROMPT
from src.agent.utils import llm_json, llm_text, classify_source, is_pdf_url
from src.tools.search import web_search
from duckduckgo_search.exceptions import RatelimitException
from src.tools.fetch import fetch_url
from src.tools.pdf import fetch_pdf_text
from src.config import settings


def add_event(state: RunState, type_: str, payload: Dict[str, Any]) -> None:
    """Append a structured event to the run's timeline for later inspection/streaming."""
    state.events.append({"type": type_, "payload": payload})

def plan_node(state: RunState) -> RunState:
    """Use the LLM to generate research angles, subquestions, and search queries."""
    add_event(state, "plan_started", {})
    data = llm_json(PLAN_PROMPT.format(prompt=state.prompt))
    state.plan = Plan(**data)
    add_event(state, "plan_created", {"angles": state.plan.angles, "queries": state.plan.queries})
    return state

def search_node(state: RunState) -> RunState:
    """
    Run web search for the current iteration using the planned queries.

    For now we always reuse the original plan queries; in later iterations you
    can extend this to incorporate follow-up queries derived from coverage gaps.
    """
    assert state.plan is not None
    add_event(state, "search_started", {"iter": state.iter})
    # Use the plan queries; if iter>0, you can append follow-up queries from coverage gaps later
    queries_to_process = state.plan.queries[:12]
    for idx, q in enumerate(queries_to_process):
        try:
            # Add delay between queries to avoid rate limits (except for first query)
            if idx > 0:
                time.sleep(1.5)  # 1.5 second delay between queries
            
            results = web_search(q, max_results=settings.TOPK_PER_QUERY)
            for r in results:
                state.search_results.append(SearchResult(query=q, title=r["title"], url=r["url"], snippet=r.get("snippet"), rank=r["rank"]))
        except RatelimitException as e:
            # If rate limit persists after retries, log and skip remaining queries
            add_event(state, "search_rate_limited", {"query": q, "error": str(e), "queries_processed": idx + 1})
            break
        except Exception as e:
            # Log other errors but continue with remaining queries
            add_event(state, "search_error", {"query": q, "error": str(e)})
            continue
    
    add_event(state, "search_done", {"total_results": len(state.search_results)})
    return state

def fetch_node(state: RunState) -> RunState:
    """Fetch and parse documents for unique URLs discovered in search results."""
    add_event(state, "fetch_started", {})
    # Dedupe URLs and cap total fetches
    seen = set(d.url for d in state.documents)
    urls = []
    for r in state.search_results:
        if r.url and r.url not in seen:
            urls.append(r.url)
            seen.add(r.url)
        if len(urls) >= 12:
            break

    for url in urls:
        try:
            if is_pdf_url(url):
                text = fetch_pdf_text(url)
                title = None
                status = 200
            else:
                status, title, text = fetch_url(url)
            if not text or len(text) < 400:
                continue
            stype = classify_source(url)
            state.documents.append(Document(url=url, title=title, text=text, status=status, source_type=stype))
            add_event(state, "doc_fetched", {"url": url, "source_type": stype, "chars": len(text)})
        except Exception as e:
            add_event(state, "doc_fetch_failed", {"url": url, "error": str(e)})
            continue
    add_event(state, "fetch_done", {"docs": len(state.documents)})
    return state

def extract_node(state: RunState) -> RunState:
    """Call the LLM to extract structured evidence snippets per angle from documents."""
    assert state.plan is not None
    add_event(state, "extract_started", {})
    # For each angle, extract from a subset of docs
    docs = state.documents[:10]
    for angle in state.plan.angles[:6]:
        for doc in docs[:5]:
            prompt = EVIDENCE_PROMPT.format(
                prompt=state.prompt,
                angle=angle,
                text=doc.text[:12000],  # cap
                url=doc.url,
            )
            try:
                items = llm_json(prompt)
                for it in items[:4]:
                    state.evidence.append(Evidence(**it))
            except Exception:
                continue
    add_event(state, "extract_done", {"evidence": len(state.evidence)})
    return state

def coverage_check_node(state: RunState) -> RunState:
    """Compute coverage metrics and record any remaining evidence/source gaps."""
    assert state.plan is not None
    add_event(state, "coverage_check_started", {})
    cov = Coverage()
    for angle in state.plan.angles:
        cov.evidence_per_angle[angle] = sum(1 for e in state.evidence if e.angle == angle)
    cov.unique_sources = len({e.url for e in state.evidence})
    cov.academic_sources = len({d.url for d in state.documents if d.source_type == "academic"})
    cov.industry_sources = len({d.url for d in state.documents if d.source_type == "industry"})

    cov.gaps = []
    for angle in state.plan.angles[:6]:
        if cov.evidence_per_angle.get(angle, 0) < settings.MIN_EVIDENCE_PER_ANGLE:
            cov.gaps.append(f"Need more evidence for angle: {angle}")
    if cov.unique_sources < settings.MIN_TOTAL_SOURCES:
        cov.gaps.append("Need more unique sources overall")
    if cov.academic_sources < settings.MIN_ACADEMIC_SOURCES:
        cov.gaps.append("Need more academic sources")
    if cov.industry_sources < settings.MIN_INDUSTRY_SOURCES:
        cov.gaps.append("Need more industry sources")

    # Record coverage summary on the run state and advance the iteration counter.
    # The LangGraph conditional in `should_loop` uses `state.iter` together with
    # `state.coverage.gaps` to decide whether to perform another search/fetch pass.
    state.coverage = cov
    state.iter += 1
    add_event(state, "coverage_check_done", state.coverage.model_dump())
    return state

def write_node(state: RunState) -> RunState:
    """Generate a first-draft Markdown research report from the collected evidence."""
    add_event(state, "write_started", {})
    evidence_json = json.dumps([e.model_dump() for e in state.evidence], indent=2)
    state.draft_report_md = llm_text(WRITE_PROMPT.format(prompt=state.prompt, evidence_json=evidence_json))
    add_event(state, "write_done", {"chars": len(state.draft_report_md or "")})
    return state

def verify_node(state: RunState) -> RunState:
    """Ask the LLM to critique the draft report and surface grounding/coverage issues."""
    add_event(state, "verify_started", {})
    evidence_json = json.dumps([e.model_dump() for e in state.evidence], indent=2)
    issues = llm_json(VERIFY_PROMPT.format(prompt=state.prompt, report_md=state.draft_report_md or "", evidence_json=evidence_json))
    state.verification_issues = [VerificationIssue(**it) for it in issues] if issues else []
    add_event(state, "verify_done", {"issues": len(state.verification_issues)})
    return state

def revise_node(state: RunState) -> RunState:
    """Optionally revise the draft report based on structured verification issues."""
    # Simple revision strategy: if verifier found issues, re-run writer with issue list appended.
    if not state.verification_issues:
        state.final_report_md = state.draft_report_md
        add_event(state, "revise_skipped", {})
        return state

    add_event(state, "revise_started", {})
    issues_text = "\n".join([f"- {i.kind}: {i.detail}" for i in state.verification_issues])
    evidence_json = json.dumps([e.model_dump() for e in state.evidence], indent=2)

    revision_prompt = WRITE_PROMPT.format(prompt=state.prompt, evidence_json=evidence_json) + f"\n\nFix these issues:\n{issues_text}\n"
    state.final_report_md = llm_text(revision_prompt)
    add_event(state, "revise_done", {"chars": len(state.final_report_md or "")})
    return state