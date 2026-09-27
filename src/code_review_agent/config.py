from functools import lru_cache

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "llama3.2"
    ollama_api_key: str = "ollama"  # unused locally; required by the OpenAI SDK

    github_token: str = ""
    github_webhook_secret: str = ""

    max_agent_iterations: int = 8
    review_severity_threshold: str = "info"

    host: str = "0.0.0.0"
    port: int = 8000

    @property
    def llm_configured(self) -> bool:
        return bool(self.ollama_model)

    @property
    def github_configured(self) -> bool:
        return bool(self.github_token)


def check_ollama_available(settings: Settings) -> bool:
    """Return True if the Ollama server is reachable."""
    base = settings.ollama_base_url.rstrip("/").removesuffix("/v1")
    try:
        response = httpx.get(f"{base}/api/tags", timeout=3.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
