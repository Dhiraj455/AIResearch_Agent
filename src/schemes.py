from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal
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

class Evidence(BaseModel):
    angle: str
    claim_type: ClaimType
    snippet: str
    url: str
    support: str  # what this snippet supports (short label)

class Coverage(BaseModel):
    evidence_per_angle: Dict[str, int] = Field(default_factory=dict)
    unique_sources: int = 0
    academic_sources: int = 0
    industry_sources: int = 0
    gaps: List[str] = Field(default_factory=list)

class VerificationIssue(BaseModel):
    kind: Literal["uncited_claim", "weak_citation", "missing_angle", "contradiction", "other"]
    detail: str

class RunState(BaseModel):
    run_id: str
    prompt: str
    iter: int = 0

    plan: Optional[Plan] = None
    search_results: List[SearchResult] = Field(default_factory=list)
    documents: List[Document] = Field(default_factory=list)
    evidence: List[Evidence] = Field(default_factory=list)

    coverage: Coverage = Field(default_factory=Coverage)
    draft_report_md: Optional[str] = None
    verification_issues: List[VerificationIssue] = Field(default_factory=list)
    final_report_md: Optional[str] = None

    events: List[dict] = Field(default_factory=list)  # for UI timeline