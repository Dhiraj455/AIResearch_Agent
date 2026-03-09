import httpx
import trafilatura
from readability import Document as ReadabilityDoc
from bs4 import BeautifulSoup
from tenacity import retry, stop_after_attempt, wait_exponential
from src.config import settings

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def fetch_url(url: str) -> tuple[int, str, str]:
    with httpx.Client(timeout=settings.REQUEST_TIMEOUT_S, follow_redirects=True) as client:
        r = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        html = r.text
    title = ""
    try:
        title = ReadabilityDoc(html).short_title()
    except Exception:
        pass
    text = extract_text(html)
    return r.status_code, title, text

def extract_text(html: str) -> str:
    # Try trafilatura first
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    if extracted and len(extracted.strip()) > 400:
        return extracted.strip()

    # Fallback: readability + soup
    doc = ReadabilityDoc(html)
    content_html = doc.summary()
    soup = BeautifulSoup(content_html, "html.parser")
    text = soup.get_text("\n", strip=True)
    return text.strip()