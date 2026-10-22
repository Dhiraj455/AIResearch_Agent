import hashlib
import json
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Tuple

from src.schemes import (
    RunState,
    Plan,
    SearchResult,
    Document,
    Evidence,
    Coverage,
    VerificationIssue,
)
from src.agent.prompt import (
    PLAN_PROMPT,
    EVIDENCE_PROMPT,
    VERIFY_CLAIMS_PROMPT,
    GAP_QUERIES_PROMPT,
    WRITE_PROMPT,
    VERIFY_PROMPT,
)
from src.agent.utils import (
    as_list,
    llm_json,
    llm_text,
    classify_source,
    MIN_QUOTE_CHARS,
    is_pdf_url,
    normalize_for_match,
    quote_in_source,
    run_parallel,
)
from src.cache import kv
from src.agent.cancel import raise_if_cancelled
from src.agent import live
from src.tools.search import web_search
from src.tools.fetch import fetch_url
from src.tools.pdf import fetch_pdf_text
from src.config import settings

_CACHE_TTL_S = settings.CACHE_TTL_HOURS * 3600
_DOC_TEXT_CAP = 12000


def add_event(state: RunState, type_: str, payload: Dict[str, Any]) -> None:
    """Append a timestamped event to the run's timeline and push it to any live listener (SSE)."""
    event = {"type": type_, "payload": payload, "ts": round(time.time(), 3)}
    state.events.append(event)
    live.publish(state.run_id, event)


def _bump(state: RunState, key: str, n: int = 1) -> None:
    state.stats[key] = state.stats.get(key, 0) + n


def _timed(state: RunState, key: str, started: float) -> None:
    state.stats.setdefault("timings_s", {})
    state.stats["timings_s"][key] = round(state.stats["timings_s"].get(key, 0) + time.time() - started, 2)


def _cache_key(prefix: str, value: str) -> str:
    return f"{prefix}:{hashlib.sha1(value.encode('utf-8')).hexdigest()}"


def _evidence_json(evidence: List[Evidence]) -> str:
    return json.dumps(
        [e.model_dump(include={"angle", "claim_type", "snippet", "url", "support"}) for e in evidence],
        indent=2,
    )


def plan_node(state: RunState) -> RunState:
    """Use the LLM to generate research angles, subquestions, and search queries."""
    started = time.time()
    add_event(state, "plan_started", {})
    data = llm_json(PLAN_PROMPT.format(prompt=state.prompt))
    state.plan = Plan(**data)
    _timed(state, "plan", started)
    add_event(state, "plan_created", {"angles": state.plan.angles, "queries": state.plan.queries})
    return state


def _next_queries(state: RunState) -> List[str]:
    """First pass uses the plan's queries; later passes ask the LLM for new queries targeting coverage gaps."""
    assert state.plan is not None
    used = set(q.lower() for q in state.used_queries)
    if state.iter == 0:
        candidates = state.plan.queries
    else:
        try:
            data = llm_json(GAP_QUERIES_PROMPT.format(
                prompt=state.prompt,
                used="\n".join(f"- {q}" for q in state.used_queries),
                gaps="\n".join(f"- {g}" for g in state.coverage.gaps) or "- Too many claims failed verification; find stronger sources",
            ))
            candidates = as_list(data)
        except Exception as e:
            add_event(state, "gap_queries_failed", {"error": str(e)})
            candidates = state.plan.queries
    fresh = []
    for q in candidates:
        if isinstance(q, str) and q.strip() and q.lower() not in used:
            fresh.append(q.strip())
            used.add(q.lower())
    return fresh[: settings.MAX_QUERIES_PER_ITER]


def _cached_search(query: str) -> Tuple[List[dict], bool]:
    key = _cache_key("search", f"{settings.TOPK_PER_QUERY}:{query}")
    raw = kv.get(key)
    if raw:
        return json.loads(raw), True
    results = web_search(query, max_results=settings.TOPK_PER_QUERY)
    kv.setex(key, _CACHE_TTL_S, json.dumps(results).encode("utf-8"))
    return results, False


def search_node(state: RunState) -> RunState:
    """Run web searches for this iteration (plan queries first, gap-driven follow-up queries later)."""
    started = time.time()
    add_event(state, "search_started", {"iter": state.iter})
    queries = _next_queries(state)
    state.used_queries.extend(queries)
    add_event(state, "search_queries", {"iter": state.iter, "queries": queries})

    before = len(state.search_results)
    for q, out, err in run_parallel(_cached_search, queries, settings.SEARCH_CONCURRENCY):
        if err is not None:
            add_event(state, "search_error", {"query": q, "error": str(err)})
            continue
        results, hit = out
        _bump(state, "search_cache_hits" if hit else "search_cache_misses")
        for r in results:
            if r.get("url"):
                state.search_results.append(SearchResult(query=q, title=r.get("title") or "", url=r["url"], snippet=r.get("snippet"), rank=r["rank"]))

    _timed(state, "search", started)
    add_event(state, "search_done", {"new_results": len(state.search_results) - before, "total_results": len(state.search_results)})
    return state


def _fetch_document(url: str) -> Tuple[Dict[str, Any], bool]:
    """Fetch and extract a URL's text, using the scrape cache (24h TTL) when possible."""
    key = _cache_key("scrape", url)
    raw = kv.get(key)
    if raw:
        return json.loads(raw), True
    if is_pdf_url(url):
        page = {"status": 200, "title": None, "text": fetch_pdf_text(url)}
    else:
        status, title, text = fetch_url(url)
        page = {"status": status, "title": title, "text": text}
    kv.setex(key, _CACHE_TTL_S, json.dumps(page).encode("utf-8"))
    return page, False


def fetch_node(state: RunState) -> RunState:
    """Fetch and parse documents for new unique URLs discovered in search results (in parallel)."""
    started = time.time()
    add_event(state, "fetch_started", {})
    seen = set(d.url for d in state.documents) | set(state.failed_urls)
    urls = []
    for r in state.search_results:
        if r.url not in seen:
            urls.append(r.url)
            seen.add(r.url)
        if len(urls) >= settings.MAX_DOCS_PER_ITER:
            break

    def fetch(url: str) -> Tuple[Dict[str, Any], bool]:
        raise_if_cancelled(state.run_id)
        return _fetch_document(url)

    for url, out, err in run_parallel(fetch, urls, settings.FETCH_CONCURRENCY):
        if err is not None:
            state.failed_urls.append(url)
            add_event(state, "doc_fetch_failed", {"url": url, "error": str(err)})
            continue
        page, hit = out
        _bump(state, "scrape_cache_hits" if hit else "scrape_cache_misses")
        text = page.get("text") or ""
        if len(text) < 400:
            state.failed_urls.append(url)
            continue
        stype = classify_source(url)
        state.documents.append(Document(url=url, title=page.get("title"), text=text, status=page.get("status"), source_type=stype))
        add_event(state, "doc_fetched", {"url": url, "source_type": stype, "chars": len(text), "cached": hit})

    _timed(state, "fetch", started)
    add_event(state, "fetch_done", {"docs": len(state.documents)})
    return state


def extract_node(state: RunState) -> RunState:
    """
    Extract verbatim-quoted evidence from each new document (one LLM call per doc, in parallel),
    then run the deterministic check: a quote not found in the scraped text is refuted outright.
    """
    assert state.plan is not None
    started = time.time()
    add_event(state, "extract_started", {})
    angles = state.plan.angles[:6]
    angle_lookup = {a.lower().strip(): a for a in angles}
    docs = [d for d in state.documents if d.url not in state.extracted_urls]

    def extract(doc: Document) -> list:
        raise_if_cancelled(state.run_id)  # skip queued work once Stop is pressed
        items = llm_json(EVIDENCE_PROMPT.format(
            prompt=state.prompt,
            angles="\n".join(f"- {a}" for a in angles),
            text=doc.text[:_DOC_TEXT_CAP],
            max_items=settings.MAX_EVIDENCE_PER_DOC,
        ))
        return as_list(items)

    new_items = 0
    quote_misses = 0
    empty_snippets = 0
    for doc, items, err in run_parallel(extract, docs, settings.LLM_CONCURRENCY):
        state.extracted_urls.append(doc.url)
        if err is not None:
            add_event(state, "extract_failed", {"url": doc.url, "error": str(err)})
            continue
        normalized = normalize_for_match(doc.text[:_DOC_TEXT_CAP])
        for it in items[: settings.MAX_EVIDENCE_PER_DOC]:
            if not isinstance(it, dict):
                continue
            angle = angle_lookup.get(str(it.get("angle", "")).lower().strip())
            snippet, support = it.get("snippet"), it.get("support")
            if not angle or not isinstance(snippet, str) or not isinstance(support, str):
                continue
            if len(snippet.strip()) < MIN_QUOTE_CHARS:
                empty_snippets += 1  # no quote given: nothing to verify, so not a refuted claim
                continue
            claim_type = it.get("claim_type")
            if claim_type not in ("benefit", "risk", "tradeoff", "best_practice"):
                claim_type = "unknown"
            found = quote_in_source(snippet, normalized)
            ev = Evidence(
                angle=angle, claim_type=claim_type, snippet=snippet, support=support,
                url=doc.url,  # never trust a model-supplied URL
                iter=state.iter, quote_found=found,
            )
            if not found:
                ev.verified = False  # deterministic check overrides any model vote
                quote_misses += 1
            state.evidence.append(ev)
            new_items += 1

    _bump(state, "empty_snippets_skipped", empty_snippets)
    _timed(state, "extract", started)
    add_event(state, "extract_done", {"new_evidence": new_items, "quote_not_found": quote_misses, "empty_snippets": empty_snippets, "evidence": len(state.evidence)})
    return state


def _verifier_models() -> List[str]:
    models = [m.strip() for m in settings.VERIFIER_MODELS.split(",") if m.strip()]
    return list(dict.fromkeys(models)) or [settings.GEMINI_MODEL]


def verify_claims_node(state: RunState) -> RunState:
    """
    Skeptic quorum: every new claim whose quote passed the deterministic check is judged by
    several independent models in parallel against the raw scraped source. Majority rule;
    a tie (or any non-majority) is treated as refuted.
    """
    started = time.time()
    add_event(state, "claims_verify_started", {})
    models = _verifier_models()
    docs_by_url = {d.url: d for d in state.documents}
    pending: Dict[str, List[Tuple[int, Evidence]]] = defaultdict(list)
    for i, ev in enumerate(state.evidence):
        if ev.verified is None and ev.url in docs_by_url:
            pending[ev.url].append((i, ev))

    def judge(task: Tuple[str, str]) -> Dict[int, str]:
        raise_if_cancelled(state.run_id)
        url, model = task
        claims = [{"id": i, "claim": ev.support, "quote": ev.snippet} for i, ev in pending[url]]
        data = llm_json(
            VERIFY_CLAIMS_PROMPT.format(url=url, text=docs_by_url[url].text[:_DOC_TEXT_CAP], claims_json=json.dumps(claims, indent=2)),
            model_name=model,
        )
        rows = as_list(data)
        out = {}
        for row in rows or []:
            if isinstance(row, dict) and row.get("verdict") in ("supported", "refuted", "unclear"):
                try:
                    out[int(row["id"])] = row["verdict"]
                except (KeyError, TypeError, ValueError):
                    continue
        return out

    # Model-major order: local servers (e.g. Ollama on one GPU) hold one model at a time, so this minimizes swaps.
    tasks = [(url, model) for model in models for url in pending]
    for (url, model), votes, err in run_parallel(judge, tasks, settings.LLM_CONCURRENCY):
        if err is not None:
            add_event(state, "verifier_failed", {"url": url, "model": model, "error": str(err)})
            continue
        for i, _ in pending[url]:
            if i in votes:
                state.evidence[i].verdicts[model] = votes[i]

    supported = refuted = unanimous = unvoted = 0
    for items in pending.values():
        for i, ev in items:
            votes = list(ev.verdicts.values())
            if not votes:
                # No verifier answered: fall back to the deterministic check alone (fail-open).
                ev.verified = True
                unvoted += 1
            else:
                ev.verified = Counter(votes)["supported"] * 2 > len(votes)
                if len(set(votes)) == 1:
                    unanimous += 1
            supported += ev.verified
            refuted += not ev.verified

    voted = supported + refuted - unvoted
    _bump(state, "claims_supported", supported)
    _bump(state, "claims_refuted_by_quorum", refuted)
    _bump(state, "claims_unanimous", unanimous)
    _bump(state, "claims_voted", voted)
    state.stats["quorum_agreement"] = round(state.stats["claims_unanimous"] / state.stats["claims_voted"], 3) if state.stats.get("claims_voted") else None
    state.stats["verifier_models"] = models
    _timed(state, "verify_claims", started)
    add_event(state, "claims_verified", {
        "supported": supported, "refuted": refuted, "unvoted": unvoted,
        "models": models, "agreement": state.stats["quorum_agreement"],
    })
    return state


def coverage_check_node(state: RunState) -> RunState:
    """Compute coverage over *verified* evidence, the latest pass's refuted ratio, and remaining gaps."""
    assert state.plan is not None
    add_event(state, "coverage_check_started", {})
    verified = state.verified_evidence()
    cov = Coverage()
    for angle in state.plan.angles:
        cov.evidence_per_angle[angle] = sum(1 for e in verified if e.angle == angle)
    cov.unique_sources = len({e.url for e in verified})
    verified_urls = {e.url for e in verified}
    cov.academic_sources = len({d.url for d in state.documents if d.source_type == "academic" and d.url in verified_urls})
    cov.industry_sources = len({d.url for d in state.documents if d.source_type == "industry" and d.url in verified_urls})
    cov.verified_claims = len(verified)
    cov.refuted_claims = sum(1 for e in state.evidence if e.verified is False)
    latest = [e for e in state.evidence if e.iter == state.iter]
    cov.last_refuted_ratio = round(sum(1 for e in latest if e.verified is False) / len(latest), 3) if latest else 0.0

    cov.gaps = []
    for angle in state.plan.angles[:6]:
        if cov.evidence_per_angle.get(angle, 0) < settings.MIN_EVIDENCE_PER_ANGLE:
            cov.gaps.append(f"Need more verified evidence for angle: {angle}")
    if cov.unique_sources < settings.MIN_TOTAL_SOURCES:
        cov.gaps.append("Need more unique sources overall")
    if cov.academic_sources < settings.MIN_ACADEMIC_SOURCES:
        cov.gaps.append("Need more academic sources")
    if cov.industry_sources < settings.MIN_INDUSTRY_SOURCES:
        cov.gaps.append("Need more industry sources")
    if cov.last_refuted_ratio > settings.MAX_REFUTED_RATIO:
        cov.gaps.append(f"{cov.last_refuted_ratio:.0%} of the latest claims failed verification; find stronger sources")

    # The LangGraph conditional in `should_loop` uses `state.iter` together with
    # `state.coverage` to decide whether to perform another search/fetch pass.
    state.coverage = cov
    state.iter += 1
    add_event(state, "coverage_check_done", state.coverage.model_dump())
    return state


def write_node(state: RunState) -> RunState:
    """Generate a first-draft Markdown research report from verified evidence only."""
    started = time.time()
    add_event(state, "write_started", {"verified_evidence": len(state.verified_evidence())})
    if not state.verified_evidence():
        # Never let the writer answer from model memory: no verified evidence means no report.
        failures = sorted({e["type"] for e in state.events if e["type"].endswith(("_error", "_failed"))})
        state.draft_report_md = state.final_report_md = (
            "# No verified evidence found\n\n"
            "The agent could not collect any claims that passed verification against their sources, "
            "so it did not write a report (writing one would mean answering from model memory).\n\n"
            f"- Search results: {len(state.search_results)}\n"
            f"- Documents fetched: {len(state.documents)}\n"
            f"- Claims extracted: {len(state.evidence)}\n"
            + (f"- Errors seen: {', '.join(failures)}\n" if failures else "")
        )
        add_event(state, "write_skipped", {"reason": "no_verified_evidence"})
        return state
    state.draft_report_md = llm_text(WRITE_PROMPT.format(prompt=state.prompt, evidence_json=_evidence_json(state.verified_evidence())))
    _timed(state, "write", started)
    add_event(state, "write_done", {"chars": len(state.draft_report_md or "")})
    return state


def verify_node(state: RunState) -> RunState:
    """Ask the LLM to critique the draft report and surface grounding/coverage issues."""
    if not state.verified_evidence():
        state.verification_issues = []  # nothing was written, so nothing to critique or revise
        return state
    add_event(state, "verify_started", {})
    try:
        issues = llm_json(VERIFY_PROMPT.format(prompt=state.prompt, report_md=state.draft_report_md or "", evidence_json=_evidence_json(state.verified_evidence())))
        state.verification_issues = [VerificationIssue(**it) for it in as_list(issues) if isinstance(it, dict)]
    except Exception as e:
        add_event(state, "verify_failed", {"error": str(e)})
        state.verification_issues = []
    add_event(state, "verify_done", {"issues": len(state.verification_issues)})
    return state


def revise_node(state: RunState) -> RunState:
    """Optionally revise the draft report based on structured verification issues."""
    # Simple revision strategy: if verifier found issues, re-run writer with issue list appended.
    if not state.verification_issues:
        state.final_report_md = state.draft_report_md
        add_event(state, "revise_skipped", {})
        return state

    started = time.time()
    add_event(state, "revise_started", {})
    issues_text = "\n".join([f"- {i.kind}: {i.detail}" for i in state.verification_issues])
    revision_prompt = WRITE_PROMPT.format(prompt=state.prompt, evidence_json=_evidence_json(state.verified_evidence())) + f"\n\nFix these issues:\n{issues_text}\n"
    state.final_report_md = llm_text(revision_prompt)
    _timed(state, "revise", started)
    add_event(state, "revise_done", {"chars": len(state.final_report_md or "")})
    return state
