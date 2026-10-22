from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, List, Dict, Optional, Literal
from datetime import datetime

SourceType = Literal["academic", "industry", "news", "blog", "docs", "unknown"]
ClaimType = Literal["benefit", "risk", "tradeoff", "best_practice", "unknown"]

class Plan(BaseModel):
    angles: List[str]
    subquestions: List[str]
    queries: List[str]

class SearchResult(BaseModel):
    query: str
    title: str
    url: str
    snippet: Optional[str] = None
    rank: int

class Document(BaseModel):
    url: str
    title: Optional[str] = None
    source_type: SourceType = "unknown"
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)
    text: str
    status: Optional[int] = None

Verdict = Literal["supported", "refuted", "unclear"]

class Evidence(BaseModel):
    angle: str
    claim_type: ClaimType = "unknown"
    snippet: str  # verbatim quote from the source
    url: str
    support: str  # the claim this quote supports
    iter: int = 0
    quote_found: Optional[bool] = None  # deterministic substring check against scraped text
    verdicts: Dict[str, Verdict] = Field(default_factory=dict)  # model name -> vote
    verified: Optional[bool] = None  # final decision; None = not checked yet

class Coverage(BaseModel):
    evidence_per_angle: Dict[str, int] = Field(default_factory=dict)
    unique_sources: int = 0
    academic_sources: int = 0
    industry_sources: int = 0
    verified_claims: int = 0
    refuted_claims: int = 0
    last_refuted_ratio: float = 0.0  # refuted share of the latest pass's claims
    gaps: List[str] = Field(default_factory=list)

class VerificationIssue(BaseModel):
    kind: Literal["uncited_claim", "weak_citation", "missing_angle", "contradiction", "other"]
    detail: str

MessageRole = Literal["user", "assistant"]


class Message(BaseModel):
    role: MessageRole
    content: str
    run_id: Optional[str] = None  # if assistant message is from a research run
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Chat(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    messages: List[Message] = Field(default_factory=list)
    last_run_id: Optional[str] = None  # latest research run, used for follow-up context


class RunState(BaseModel):
    run_id: str
    prompt: str
    iter: int = 0

    plan: Optional[Plan] = None
    search_results: List[SearchResult] = Field(default_factory=list)
    documents: List[Document] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)
    used_queries: List[str] = Field(default_factory=list)
    extracted_urls: List[str] = Field(default_factory=list)
    failed_urls: List[str] = Field(default_factory=list)

    coverage: Coverage = Field(default_factory=Coverage)
    draft_report_md: Optional[str] = None
    verification_issues: List[VerificationIssue] = Field(default_factory=list)
    final_report_md: Optional[str] = None

    events: List[dict] = Field(default_factory=list)  # for UI timeline
    stats: Dict[str, Any] = Field(default_factory=dict)  # cache hits, timings, quorum agreement

    def verified_evidence(self) -> List[Evidence]:
        return [e for e in self.evidence if e.verified]