"""Typed settings. API and worker settings are separate classes so the API
process can never be configured with the service-role database URL."""

from typing import Self

from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from somnia.memory.tokenizer import TokenEncoding

_ENV = SettingsConfigDict(env_prefix="SOMNIA_", env_file=".env", extra="ignore")


class ProviderSettings(BaseSettings):
    model_config = _ENV

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    request_timeout_s: float = 60.0


class ApiSettings(BaseSettings):
    model_config = _ENV

    api_database_url: SecretStr
    supabase_url: AnyHttpUrl | None = None
    supabase_publishable_key: SecretStr | None = None
    pool_max_size: int = Field(default=10, ge=1)
    recency_half_life_days: float = Field(default=30.0, gt=0)
    default_token_budget: int = Field(default=2000, ge=1)
    token_encoding: TokenEncoding = "o200k_base"
    dream_interval_s: float = Field(default=3600.0, gt=0)  # shown in the admin UI
    candidate_pool_factor: int = Field(default=4, ge=1)
    chunk_weight: float = Field(default=0.5, ge=0, le=1)  # undreamt chunks rank below memories
    chunk_dedupe_similarity: float = Field(default=0.9, ge=0, le=1)

    @model_validator(mode="after")
    def dashboard_auth_is_configured_together(self) -> Self:
        if bool(self.supabase_url) != bool(
            self.supabase_publishable_key and self.supabase_publishable_key.get_secret_value()
        ):
            raise ValueError("set both SOMNIA_SUPABASE_URL and SOMNIA_SUPABASE_PUBLISHABLE_KEY")
        return self


class DreamPolicy(BaseModel):
    similarity_threshold: float = Field(default=0.85, ge=0, le=1)
    merge_confidence_boost: float = Field(default=0.1, ge=0, le=1)
    decay_after_days: float = Field(default=14.0, gt=0)
    decay_factor: float = Field(default=0.9, gt=0, le=1)
    min_confidence: float = Field(default=0.05, ge=0, le=1)


class WorkerSettings(BaseSettings, DreamPolicy):
    model_config = _ENV

    service_database_url: SecretStr
    ingest_batch_size: int = Field(default=100, ge=1)
    chunk_max_chars: int = Field(default=1200, ge=100)
    chunk_overlap_chars: int = Field(default=150, ge=0)
    poll_interval_s: float = Field(default=2.0, gt=0)
    dream_interval_s: float = Field(default=3600.0, gt=0)
    idle_minutes: float = Field(default=30.0, gt=0)  # open session quiet this long -> dream
    chunk_threshold: int = Field(default=200, ge=1)  # undreamt chunks per repo -> dream
