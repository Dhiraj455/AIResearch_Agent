import json, re, uuid, unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from typing import Any, Callable, Iterable, Iterator, List, Optional, Tuple, TypeVar

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_random_exponential

from src.config import settings

T = TypeVar("T")
R = TypeVar("R")

if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)

_gemini_models: dict[str, genai.GenerativeModel] = {}
_openai_client = None


def _gemini(model_name: str) -> genai.GenerativeModel:
    """Return a cached Gemini model instance."""
    if not settings.GEMINI_API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Please add it to your environment or .env file."
        )
    if model_name not in _gemini_models:
        _gemini_models[model_name] = genai.GenerativeModel(model_name)
    return _gemini_models[model_name]


def _openai():
    """Lazily create the OpenAI client for `openai:` models (OpenAI, or an OpenAI-compatible server like Ollama)."""
    global _openai_client
    if _openai_client is None:
        if not settings.OPENAI_API_KEY and not settings.OPENAI_BASE_URL:
            raise RuntimeError("Set OPENAI_API_KEY (or OPENAI_BASE_URL for a local server) to use `openai:` models.")
        from openai import OpenAI

        _openai_client = OpenAI(
            # Local servers such as Ollama ignore the key, but the client requires one.
            api_key=settings.OPENAI_API_KEY or "local",
            base_url=settings.OPENAI_BASE_URL or None,
            timeout=settings.LLM_TIMEOUT_S,
        )
    return _openai_client


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


@retry(stop=stop_after_attempt(3), wait=wait_random_exponential(multiplier=1, max=20), reraise=True)
def _generate(prompt: str, temperature: float, model_name: Optional[str] = None, json_mode: bool = False) -> str:
    """
    Call an LLM and return its text. Retries with exponential backoff + jitter.

    Model names prefixed with `openai:` go to OpenAI; everything else is a Gemini model.
    """
    name = model_name or settings.GEMINI_MODEL
    if name.startswith("openai:"):
        kwargs: dict[str, Any] = {"response_format": {"type": "json_object"}} if json_mode else {}
        resp = _openai().chat.completions.create(
            model=name.removeprefix("openai:"),
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            **kwargs,
        )
        return (resp.choices[0].message.content or "").strip()

    config: dict[str, Any] = {"temperature": temperature}
    if json_mode:
        config["response_mime_type"] = "application/json"
    response = _gemini(name).generate_content(
        prompt,
        generation_config=config,
        request_options={"timeout": settings.LLM_TIMEOUT_S},
    )
    return (response.text or "").strip()


def llm_json(prompt: str, model_name: Optional[str] = None) -> Any:
    """Ask the LLM for JSON (native JSON mode on Gemini) and parse it."""
    return parse_json(_generate(prompt, temperature=0.2, model_name=model_name, json_mode=True))


def llm_text(prompt: str, fast: bool = False) -> str:
    """Get free-form Markdown/text from the LLM (Gemini). Use fast=True for follow-ups."""
    model_name = (settings.GEMINI_MODEL_FAST or settings.GEMINI_MODEL) if fast else settings.GEMINI_MODEL
    return _generate(prompt, temperature=0.3, model_name=model_name)


def parse_json(text: str) -> Any:
    """Parse JSON directly; fall back to the first decodable JSON value embedded in the text."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return extract_json(text)


def as_list(data: Any) -> list:
    """
    Return a JSON array result. JSON-object mode (OpenAI-compatible servers) can wrap
    arrays as {"items": [...]}, so unwrap the first list-valued field.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def extract_json(text: str) -> Any:
    # best-effort: decode the first complete JSON object/array in the response
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                obj, _ = decoder.raw_decode(text, i)
                return obj
            except json.JSONDecodeError:
                continue
    raise ValueError("No JSON found in model output.")


def run_parallel(fn: Callable[[T], R], items: Iterable[T], max_workers: int) -> Iterator[Tuple[T, Optional[R], Optional[Exception]]]:
    """
    Run `fn` over items concurrently, isolating failures.

    Yields (item, result, error) tuples as each one completes (so callers can report progress live);
    exactly one of result/error is set.
    """
    items = list(items)
    if not items:
        return

    def safe(item: T) -> Tuple[T, Optional[R], Optional[Exception]]:
        try:
            return item, fn(item), None
        except Exception as e:
            return item, None, e

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(items)))) as pool:
        for future in as_completed([pool.submit(safe, item) for item in items]):
            yield future.result()


_QUOTE_CHARS = str.maketrans({
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "—": "-", " ": " ",
})


MIN_QUOTE_CHARS = 15  # shorter quotes (or fragments) are too generic to verify


def normalize_for_match(text: str) -> str:
    """Normalize text for verbatim quote matching (unicode, quotes/dashes, case, whitespace)."""
    text = unicodedata.normalize("NFKC", text).translate(_QUOTE_CHARS).lower()
    return re.sub(r"\s+", " ", text).strip()


def quote_in_source(quote: str, normalized_source: str) -> bool:
    """
    Deterministic check that a quote appears verbatim in the (normalized) source text.

    Quotes with ellipses are split into fragments; every substantial fragment must appear.
    """
    q = normalize_for_match(quote).strip(" \"'")
    fragments = [f.strip(" .,;:\"'") for f in re.split(r"\.{3}|…", q)]
    fragments = [f for f in fragments if len(f) >= MIN_QUOTE_CHARS]
    if not fragments:
        return False
    return all(f in normalized_source for f in fragments)


def is_pdf_url(url: str) -> bool:
    return url.lower().split("?")[0].endswith(".pdf")

# Domain lists match the host itself or any subdomain (e.g. "ai.meta.com" matches "meta.com").
_ACADEMIC_DOMAINS = {
    "arxiv.org", "acm.org", "ieee.org", "aclanthology.org", "openreview.net", "neurips.cc", "aaai.org",
    "mlr.press", "jmlr.org", "nature.com", "science.org", "sciencedirect.com", "springer.com",
    "wiley.com", "tandfonline.com", "mdpi.com", "frontiersin.org", "plos.org", "sagepub.com",
    "cambridge.org", "oup.com", "biorxiv.org", "medrxiv.org", "ssrn.com", "semanticscholar.org",
    "researchgate.net", "ncbi.nlm.nih.gov", "nih.gov", "nist.gov", "hal.science", "papers.nips.cc",
}
_INDUSTRY_DOMAINS = {
    "openai.com", "anthropic.com", "deepmind.com", "deepmind.google", "research.google", "blog.google",
    "cloud.google.com", "microsoft.com", "meta.com", "aws.amazon.com", "amazon.science", "nvidia.com",
    "ibm.com", "databricks.com", "huggingface.co", "cohere.com", "mistral.ai", "pinecone.io",
    "langchain.com", "llamaindex.ai", "weaviate.io", "elastic.co", "mongodb.com", "snowflake.com",
    "salesforce.com", "oracle.com", "redhat.com", "intel.com", "apple.com", "netflixtechblog.com",
    "uber.com", "gartner.com", "mckinsey.com", "deloitte.com", "accenture.com", "bcg.com", "forrester.com",
}
_NEWS_DOMAINS = {
    "reuters.com", "bloomberg.com", "techcrunch.com", "venturebeat.com", "wired.com", "theverge.com",
    "zdnet.com", "arstechnica.com", "forbes.com", "nytimes.com", "theguardian.com", "bbc.com",
    "bbc.co.uk", "ft.com", "wsj.com", "cnbc.com", "infoworld.com", "technologyreview.com",
}
_BLOG_PLATFORMS = {
    "medium.com", "substack.com", "dev.to", "towardsdatascience.com", "hashnode.dev", "wordpress.com",
    "blogspot.com", "dzone.com", "hackernoon.com", "analyticsvidhya.com", "freecodecamp.org", "scribd.com",
}


def _host_in(host: str, domains: set) -> bool:
    return any(host == d or host.endswith("." + d) for d in domains)


def classify_source(url: str) -> str:
    """Classify a source by its host (and path for company blogs/docs)."""
    parsed = urlparse(url.lower())
    host = (parsed.hostname or "").removeprefix("www.")
    path = parsed.path
    if _host_in(host, _ACADEMIC_DOMAINS) or host.endswith(".edu") or ".edu." in host or ".ac." in host:
        return "academic"
    if _host_in(host, _INDUSTRY_DOMAINS):
        return "industry"
    if _host_in(host, _NEWS_DOMAINS):
        return "news"
    if _host_in(host, _BLOG_PLATFORMS):
        return "blog"
    if host.startswith(("docs.", "developer.", "developers.")) or "readthedocs" in host or path.startswith("/docs"):
        return "docs"
    # A blog or engineering post on an organization's own domain counts as an industry source.
    if host.startswith(("blog.", "engineering.", "research.")) or "/blog" in path or "/engineering" in path:
        return "industry"
    return "unknown"
