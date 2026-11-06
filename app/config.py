from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    # OpenAI-compatible API base, e.g. Ollama: http://100.x.x.x:11434/v1 (Tailscale host)
    openai_api_base: str = ""
    openai_model: str = "gpt-4o-mini"

    tavily_api_key: str = ""
    serper_api_key: str = ""
    firecrawl_api_key: str = ""

    database_url: str = "postgresql+asyncpg://research:research@localhost:5432/research_engine"

    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    max_research_iterations: int = 3

    @property
    def llm_configured(self) -> bool:
        # API key (incl. dummy values like "ollama") or a custom base URL (local / Ollama / LiteLLM)
        return bool(self.openai_api_key.strip() or self.openai_api_base.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
