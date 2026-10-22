from tenacity import retry, stop_after_attempt, wait_random_exponential

# `ddgs` is the maintained successor of `duckduckgo_search` (the old package is rate-limited by DuckDuckGo).
try:
    from ddgs import DDGS
except ImportError:  # fall back until `pip install ddgs` has been run
    from duckduckgo_search import DDGS


@retry(stop=stop_after_attempt(3), wait=wait_random_exponential(multiplier=2, max=30), reraise=True)
def web_search(query: str, max_results: int = 5):
    """Web search via DDGS, retried with exponential backoff + jitter."""
    results = []
    for i, r in enumerate(DDGS().text(query, max_results=max_results) or []):
        url = r.get("href") or r.get("url")
        if not url:
            continue
        results.append({
            "title": r.get("title"),
            "url": url,
            "snippet": r.get("body"),
            "rank": i + 1,
        })
    return results
