# AI Research Agent

Web research agent that plans, searches, fetches, and synthesizes evidence into grounded Markdown reports with a ChatGPT-like chat interface.

## Quick Start

### Backend (FastAPI)

```bash
# From project root
pip install -r requirements.txt
# Set GEMINI_API_KEY and REDIS_URL in .env
uvicorn src.app:app --reload --host 0.0.0.0 --port 8000
```

Required env vars (example `.env`):

```bash
GEMINI_API_KEY=...
REDIS_URL=redis://localhost:6379/0
# Optional (defaults to 24)
CACHE_TTL_HOURS=24
```

### Frontend (Next.js)

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). The frontend talks to the backend at `http://localhost:8000` by default. Set `NEXT_PUBLIC_API_URL` in `frontend/.env.local` if your API runs elsewhere.

### Usage

1. Enter a research question in the input and press Send.
2. Wait 5–10 minutes for the full research pipeline (search, fetch, extract, write, verify).
3. View the report with citations.
4. Ask follow-up questions in the same chat for quick answers based on the report.
