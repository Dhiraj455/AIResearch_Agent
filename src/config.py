from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    MODEL: str = "gpt-4.1-mini"
    # Any OpenAI-compatible server for "openai:" models, e.g. Ollama: http://localhost:11434/v1
    OPENAI_BASE_URL: str = ""

    # Primary LLM configuration (Google Gemini).
    GEMINI_API_KEY: str = ""
    # Main model. Use "openai:<model>" for OpenAI or an OpenAI-compatible server (e.g. "openai:qwen2.5:7b" on Ollama).
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_MODEL_FAST: str = ""  # If set, used for follow-ups (e.g. gemini-2.0-flash) for faster response

    # In-memory cache TTL (hours). Data is removed after expiry.
    CACHE_TTL_HOURS: int = 24

    # Redis cache (optional). Example: redis://localhost:6379/0
    # If empty or unreachable, an in-process TTL cache is used instead (fail-open).
    REDIS_URL: str = ""

    # Legacy paths (unused when using cache; kept for reference)
    RUNS_DIR: str = "src/runs"
    CHATS_DIR: str = "src/chats"

    JWT_SECRET: str = "change-me-in-production-use-env-var"
    CORS_ORIGINS: str = "http://localhost:3000,https://ai-research-agent-iuxv.vercel.app"  # Comma-separated list for production (e.g. https://yourapp.vercel.app)
    MAX_ITERS: int = 3
    TOPK_PER_QUERY: int = 5
    MIN_EVIDENCE_PER_ANGLE: int = 2
    MIN_TOTAL_SOURCES: int = 6
    MIN_ACADEMIC_SOURCES: int = 2
    MIN_INDUSTRY_SOURCES: int = 2
    REQUEST_TIMEOUT_S: int = 20
    LLM_TIMEOUT_S: int = 120

    # Skeptic quorum: comma-separated verifier models voting on every claim.
    # Gemini model names use GEMINI_API_KEY; prefix with "openai:" to use OPENAI_API_KEY.
    VERIFIER_MODELS: str = "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash"
    # Re-investigate while more than this fraction of the latest pass's claims is refuted.
    MAX_REFUTED_RATIO: float = 0.3

    # Per-iteration caps and concurrency
    MAX_QUERIES_PER_ITER: int = 12
    MAX_DOCS_PER_ITER: int = 12
    MAX_EVIDENCE_PER_DOC: int = 8
    SEARCH_CONCURRENCY: int = 2
    FETCH_CONCURRENCY: int = 8
    LLM_CONCURRENCY: int = 6

    class Config:
        env_file = ".env"


settings = Settings()