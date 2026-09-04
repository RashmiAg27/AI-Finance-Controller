from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_ROOT / ".env"), extra="ignore")

    database_url: str = f"sqlite:///{(BACKEND_ROOT / 'finance_controller.db').as_posix()}"
    data_root: Path = PROJECT_ROOT / "data"
    configs_root: Path = BACKEND_ROOT / "configs" / "clients"

    # Comma-separated list of allowed frontend origins for CORS. Defaults to
    # the local Vite dev server; a deployed frontend's real origin (e.g.
    # https://your-app.vercel.app) must be added via CORS_ORIGINS in .env or
    # the hosting platform's environment variables -- see app.main.
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Four providers exist to prove the abstraction is real rather than
    # hard-wired to one vendor. Which one is active is decided by
    # agent_provider, or failing that by whichever key is present -- see
    # app.agent.provider.get_provider.
    gemini_api_key: str | None = None
    # gemini-2.5-flash is closed to new API keys and returns 404 for them, so
    # the default has to be a currently-available model. Override with
    # GEMINI_MODEL in .env if your key is entitled to a different one.
    gemini_model: str = "gemini-3.6-flash"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"

    openai_api_key: str | None = None
    openai_model: str = "gpt-5"

    # Groq speaks the OpenAI chat-completions API, so it reuses OpenAIProvider
    # with a different base_url rather than a separate translation layer --
    # see app.agent.provider.get_provider.
    groq_api_key: str | None = None
    # Groq's model lineup turns over quickly -- llama-3.3-70b-versatile, an
    # earlier default here, has since been decommissioned. gpt-oss-120b is
    # confirmed (2026-09-05) to exist and support tool calling on a free key;
    # if it 404s later, check GROQ_API_KEY's available models at
    # console.groq.com and override with GROQ_MODEL in .env.
    groq_model: str = "openai/gpt-oss-120b"

    # Force one provider regardless of which keys happen to be present:
    # "gemini" | "anthropic" | "openai" | "groq". Empty means auto-detect,
    # first key found wins in that order.
    agent_provider: str | None = None

    log_level: str = "INFO"

    # Deliberate pause between pipeline stages in a background batch run, so
    # an operator watching the Reconciliation window actually sees the batch
    # move through IMPORT -> MATCH -> EXCEPTIONS rather than blinking from
    # CREATED to CLOSED. Set to 0 for tests and benchmarking.
    batch_stage_delay_seconds: float = 0.45


settings = Settings()
