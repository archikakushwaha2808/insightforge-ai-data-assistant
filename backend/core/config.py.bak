import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    APP_NAME = "InsightForge AI"
    SECRET_KEY = os.getenv("SECRET_KEY", "change-this-in-production-please")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./insightforge.db")

    # Groq (free tier: https://console.groq.com/keys)
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    # NOTE: llama-3.3-70b-versatile (originally requested) was deprecated by
    # Groq in June 2026. Defaulting to openai/gpt-oss-120b instead — Groq's
    # own recommended replacement — to avoid shipping a dead model again.
    # Set GROQ_MODEL in .env to override.
    GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.2"))
    # Set to 800 per current request. Note: a "generate N SQL queries" reply
    # now has to cover N short explanations in one response, so 800 is
    # tighter than the 3000 used previously — raise GROQ_MAX_TOKENS in .env
    # if replies start getting cut off for large N.
    GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "800"))
    # Per-request timeout (seconds) passed to the Groq client. If the API
    # hasn't responded within this window we raise AssistantTimeoutError
    # instead of letting the request hang until a reverse proxy kills it
    # with a bare 502.
    GROQ_TIMEOUT_SECONDS = float(os.getenv("GROQ_TIMEOUT_SECONDS", "90"))

    # AI Insights (Workspace → "AI Insights" tab) uses its own model/token
    # budget, kept separate from GROQ_MODEL/GROQ_MAX_TOKENS above so this
    # change can't alter the existing chat assistant's behavior. It sends a
    # single one-shot request built only from the dataset's statistical
    # profile (never the chat history), so a larger token budget here is
    # safe and won't affect chat token usage.
    GROQ_INSIGHTS_MODEL = os.getenv("GROQ_INSIGHTS_MODEL", "openai/gpt-oss-20b")
    GROQ_INSIGHTS_TEMPERATURE = float(os.getenv("GROQ_INSIGHTS_TEMPERATURE", "0.2"))
    GROQ_INSIGHTS_MAX_TOKENS = int(os.getenv("GROQ_INSIGHTS_MAX_TOKENS", "12000"))

    UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "storage", "uploads")
    MAX_UPLOAD_MB = 50

settings = Settings()
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
