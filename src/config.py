from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Keep OpenAI settings so it's easy to switch back later if desired.
    OPENAI_API_KEY: str = ""
    MODEL: str = "gpt-4.1-mini"  # used only by the commented OpenAI client

    # Primary LLM configuration (Google Gemini).
    GEMINI_API_KEY: str = ""
    # Use a widely available default; can be overridden via env/GEMINI_MODEL.
    GEMINI_MODEL: str = "gemini-1.5-flash"

    RUNS_DIR: str = "src/runs"
    MAX_ITERS: int = 3
    TOPK_PER_QUERY: int = 5
    MIN_EVIDENCE_PER_ANGLE: int = 2
    MIN_TOTAL_SOURCES: int = 6
    MIN_ACADEMIC_SOURCES: int = 2
    MIN_INDUSTRY_SOURCES: int = 2
    REQUEST_TIMEOUT_S: int = 20

    class Config:
        env_file = ".env"


settings = Settings()