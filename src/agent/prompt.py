PLAN_PROMPT = """You are a web research agent.
Given the user prompt, produce:
1) 5-8 research angles
2) 6-10 subquestions
3) 8-14 search queries that cover academia + industry

Return STRICT JSON with keys: angles, subquestions, queries.
Prompt: {prompt}
"""

EVIDENCE_PROMPT = """You are extracting evidence from a source for a research report.

User prompt:
{prompt}

Research angles (use these exact strings for "angle"):
{angles}

Source text:
<<<
{text}
>>>

Extract up to {max_items} evidence items relevant to any of the angles.
Rules:
- "snippet" MUST be an exact, verbatim quote copied character-for-character from the source text
  (1-3 sentences). Do not paraphrase, merge sentences, or fix typos. Quotes not found verbatim are discarded.
- "support" is the short claim (one sentence) that the quote directly supports.
- claim_type: benefit|risk|tradeoff|best_practice|unknown
- If nothing relevant is in the text, return an empty array.

Return STRICT JSON object: {{"items": [{{"angle": "...", "claim_type": "...", "snippet": "...", "support": "..."}}]}}
"""

VERIFY_CLAIMS_PROMPT = """You are a skeptical fact-checker. For each claim below, decide whether the SOURCE TEXT
directly supports the claim using its quote. Judge only against the source text, never prior knowledge.

- supported: the quote is in the source and clearly supports the claim as stated
- refuted: the quote is missing/altered, or the claim overstates, distorts, or contradicts the source
- unclear: the source is related but does not clearly establish the claim

Source URL: {url}
Source text:
<<<
{text}
>>>

Claims:
{claims_json}

Return STRICT JSON object: {{"verdicts": [{{"id": <claim id>, "verdict": "supported|refuted|unclear"}}]}}
"""

GAP_QUERIES_PROMPT = """You are a web research agent refining a search after a previous pass.

User prompt:
{prompt}

Queries already used (do not repeat these):
{used}

Gaps to fill:
{gaps}

Write 4-8 NEW web search queries targeting these gaps. When academic or industry sources are missing,
target papers (e.g. arXiv, ACM, IEEE) or company engineering blogs and reports.

Return STRICT JSON object: {{"queries": ["..."]}}
"""

WRITE_PROMPT = """Write a Markdown research report answering the user's prompt.

Rules:
- Organize by angles (benefits, risks, bias, evaluation, best practices).
- Every major claim must be backed by at least one citation: (Source: URL).
- Explicitly separate "Claims" from "Evidence" bullets.
- Include a References section listing all unique URLs used.

User prompt:
{prompt}

Evidence objects:
{evidence_json}
"""

VERIFY_PROMPT = """You are verifying a research report for grounding and completeness.

User prompt:
{prompt}

Report:
{report_md}

Evidence objects:
{evidence_json}

Find issues:
- uncited_claim: claim without a nearby (Source: URL)
- missing_angle: major angle not covered
- weak_citation: citation exists but doesn't match the claim
- contradiction: report asserts certainty despite conflicting evidence

Return STRICT JSON object: {{"issues": [{{"kind": "...", "detail": "..."}}]}}
"""

FOLLOWUP_PROMPT = """You are a research assistant. The user previously received a research report and is asking a follow-up question.

Use the research report and evidence below to answer their question. Stay grounded in the sources; cite URLs when relevant.
If the question goes beyond the report, say so and offer what you can from the available evidence.

Research report:
{report_md}

Evidence (snippets with URLs):
{evidence_json}

User's follow-up question:
{question}

Answer in Markdown, concisely but thoroughly.
"""