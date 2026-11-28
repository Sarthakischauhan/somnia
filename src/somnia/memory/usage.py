"""Record model-provider usage. Prices come from the model catalog."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from core_ai.models.pricing import MILLION, model_price
from core_ai.types import StreamEvent
from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.client import Conn

# gemini-embedding-001 has no entry in the shared catalog. Google's published
# Gemini Developer API text rate is USD per million input tokens.
_EMBEDDING_RATES = {"gemini-embedding-001": Decimal("0.15")}


@dataclass(frozen=True)
class UsageRecord:
    provider: str
    model: str
    operation: str
    requests: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    @property
    def model_id(self) -> str:
        return f"{self.provider}:{self.model}"

    @property
    def cost_usd(self) -> Decimal:
        if self.operation == "embedding":
            rate = _EMBEDDING_RATES.get(self.model, Decimal(0))
            return Decimal(self.input_tokens) * rate / MILLION
        price = model_price(self.model_id)
        if price is None:
            return Decimal(0)
        cached = max(self.cache_read_tokens, 0)
        written = max(self.cache_write_tokens, 0)
        fresh = max(self.input_tokens - cached - written, 0)
        read_rate = price.input if price.cache_read is None else price.cache_read
        write_rate = price.input if price.cache_write is None else price.cache_write
        amount = (
            Decimal(fresh) * Decimal(str(price.input))
            + Decimal(max(self.output_tokens, 0)) * Decimal(str(price.output))
            + Decimal(max(self.reasoning_tokens, 0)) * Decimal(str(price.output))
            + Decimal(cached) * Decimal(str(read_rate))
            + Decimal(written) * Decimal(str(write_rate))
        )
        return amount / MILLION


def usage_from_event(provider: str, model: str, event: StreamEvent) -> UsageRecord:
    return UsageRecord(
        provider=provider,
        model=model,
        operation="chat",
        input_tokens=event.prompt_tokens or 0,
        output_tokens=event.completion_tokens or 0,
        reasoning_tokens=event.reasoning_tokens or 0,
        cache_read_tokens=event.cache_read_tokens or 0,
        cache_write_tokens=event.cache_write_tokens or 0,
    )


def flush_usage(conn: Conn, user_id: UUID, embedder: object, llm: object) -> None:
    records: list[UsageRecord] = []
    embedding_usage = getattr(embedder, "usage", None)
    if isinstance(embedding_usage, UsageRecord) and embedding_usage.requests:
        records.append(embedding_usage)
        if hasattr(embedder, "usage"):
            embedder.usage = UsageRecord(
                provider=embedding_usage.provider,
                model=embedding_usage.model,
                operation="embedding",
            )
    calls = getattr(llm, "calls", None)
    if isinstance(calls, list):
        records.extend(call for call in calls if isinstance(call, UsageRecord))
        calls.clear()
    for usage in records:
        record_usage(conn, user_id, usage)


class UsageModelSummary(BaseModel):
    provider: str
    model: str
    operation: Literal["chat", "embedding"]
    requests: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: Decimal


class UsageSummary(BaseModel):
    since: datetime
    models: list[UsageModelSummary]
    requests: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


def usage_summary(conn: Conn, now: datetime, days: int) -> UsageSummary:
    since = now - timedelta(days=days)
    with conn.cursor(row_factory=class_row(UsageModelSummary)) as cur:
        cur.execute(
            "select * from public.somnia_usage_summary(%s) order by cost_usd desc", (since,)
        )
        models = cur.fetchall()
    return UsageSummary(
        since=since,
        models=models,
        requests=sum(model.requests for model in models),
        input_tokens=sum(model.input_tokens for model in models),
        output_tokens=sum(model.output_tokens for model in models),
        cost_usd=sum((model.cost_usd for model in models), Decimal(0)),
    )


def record_usage(conn: Conn, user_id: UUID, usage: UsageRecord) -> None:
    conn.execute(
        "insert into public.model_usage (user_id, provider, model, operation, requests,"
        " input_tokens, output_tokens, reasoning_tokens, cache_read_tokens,"
        " cache_write_tokens, cost_usd) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            user_id,
            usage.provider,
            usage.model,
            usage.operation,
            usage.requests,
            usage.input_tokens,
            usage.output_tokens,
            usage.reasoning_tokens,
            usage.cache_read_tokens,
            usage.cache_write_tokens,
            usage.cost_usd,
        ),
    )
