import httpx
from pypdf import PdfReader
from io import BytesIO
from src.config import settings

def fetch_pdf_text(url: str) -> str:
    with httpx.Client(timeout=settings.REQUEST_TIMEOUT_S, follow_redirects=True) as client:
        r = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.content
    reader = PdfReader(BytesIO(data))
    parts = []
    for page in reader.pages[:20]:  # cap to avoid huge PDFs
        parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()