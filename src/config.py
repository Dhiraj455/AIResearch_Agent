from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    OPENAI_API_KEY: str = ""
    MODEL: str = "gpt-4.1-mini"

    # Primary LLM configuration (Google Gemini).
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"
    GEMINI_MODEL_FAST: str = ""  # If set, used for follow-ups (e.g. gemini-2.0-flash) for faster response

    RUNS_DIR: str = "src/runs"
    CHATS_DIR: str = "src/chats"
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