import json, re, uuid
from typing import Any

import google.generativeai as genai

from src.config import settings

# --- OpenAI client (kept for easy switching later, but not used now) ---
# from openai import OpenAI
# openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)


def _get_gemini_model():
    """Configure and return a Gemini model instance using settings."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Please add it to your environment or .env file."
        )
    genai.configure(api_key=settings.GEMINI_API_KEY)
    return genai.GenerativeModel(settings.GEMINI_MODEL)


_gemini_model = _get_gemini_model()


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _call_gemini(prompt: str, temperature: float) -> str:
    """Internal helper to call Gemini and return plain text content."""
    response = _gemini_model.generate_content(
        prompt,
        generation_config={"temperature": temperature},
    )
    # `response.text` is a convenience property provided by google-generativeai.
    return (response.text or "").strip()


def llm_json(prompt: str) -> Any:
    """
    Ask the LLM (Gemini) for JSON and parse it.

    We still use a simple "find first JSON object/array" strategy so that
    the rest of the code works the same way as before.
    """
    text = _call_gemini(prompt, temperature=0.2)
    return json.loads(extract_json(text))


def llm_text(prompt: str) -> str:
    """Get free-form Markdown/text from the LLM (Gemini)."""
    return _call_gemini(prompt, temperature=0.3)

def extract_json(text: str) -> str:
    # best-effort: find first JSON object/array in the response
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if not m:
        raise ValueError("No JSON found in model output.")
    return m.group(1)

def is_pdf_url(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")

def classify_source(url: str) -> str:
    u = url.lower()
    if "arxiv.org" in u or "acm.org" in u or "ieee.org" in u or ".edu" in u:
        return "academic"
    if "openai.com" in u or "deepmind" in u or "microsoft.com" in u or "meta.com" in u or "anthropic.com" in u:
        return "industry"
    if "docs" in u:
        return "docs"
    return "unknown"