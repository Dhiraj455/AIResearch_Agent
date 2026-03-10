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

Angle to focus:
{angle}

Source text (may be long):
{text}

Extract 2-6 evidence items relevant to the angle.
Each evidence item must be a short snippet (1-3 sentences max) copied/paraphrased closely from the text,
plus:
- claim_type: benefit|risk|tradeoff|best_practice|unknown
- support: a short label of what it supports (e.g., "distribution shift harms")
- url: {url}

Return STRICT JSON array of objects with keys: angle, claim_type, snippet, url, support.
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

Return STRICT JSON array of objects with keys: kind, detail.
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