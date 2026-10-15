"""Typed settings. API and worker settings are separate classes so the API
process can never be configured with the service-role database URL."""

from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from somnia.retrieval.tokenizer import TokenEncoding

_ENV = SettingsConfigDict(env_prefix="SOMNIA_", env_file=".env", extra="ignore")


class ProviderSettings(BaseSettings):
    model_config = _ENV

    provider: Literal["openai", "fake"] = "fake"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: SecretStr = SecretStr("")
    chat_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    request_timeout_s: float = 60.0


class ApiSettings(BaseSettings):
    model_config = _ENV

    api_database_url: SecretStr
    pool_max_size: int = Field(default=10, ge=1)
    recency_half_life_days: float = Field(default=30.0, gt=0)
    default_token_budget: int = Field(default=2000, ge=1)
    token_encoding: TokenEncoding = "o200k_base"
    dream_interval_s: float = Field(default=3600.0, gt=0)  # shown in the admin UI
    candidate_pool_factor: int = Field(default=4, ge=1)


class WorkerSettings(BaseSettings):
    model_config = _ENV

    service_database_url: SecretStr
    ingest_batch_size: int = Field(default=100, ge=1)
    chunk_max_chars: int = Field(default=1200, ge=100)
    chunk_overlap_chars: int = Field(default=150, ge=0)
    poll_interval_s: float = Field(default=2.0, gt=0)
    dream_interval_s: float = Field(default=3600.0, gt=0)
    similarity_threshold: float = Field(default=0.85, ge=0, le=1)
    merge_confidence_boost: float = Field(default=0.1, ge=0, le=1)
    decay_after_days: float = Field(default=14.0, gt=0)
    decay_factor: float = Field(default=0.9, gt=0, le=1)
    min_confidence: float = Field(default=0.05, ge=0, le=1)
