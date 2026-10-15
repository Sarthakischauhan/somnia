"""Tunable knobs for a dream run."""

from pydantic import BaseModel, Field

from somnia.config import WorkerSettings


class DreamPolicy(BaseModel):
    similarity_threshold: float = Field(default=0.85, ge=0, le=1)
    merge_confidence_boost: float = Field(default=0.1, ge=0, le=1)
    decay_after_days: float = Field(default=14.0, gt=0)
    decay_factor: float = Field(default=0.9, gt=0, le=1)
    min_confidence: float = Field(default=0.05, ge=0, le=1)

    @classmethod
    def from_settings(cls, settings: WorkerSettings) -> "DreamPolicy":
        return cls(
            similarity_threshold=settings.similarity_threshold,
            merge_confidence_boost=settings.merge_confidence_boost,
            decay_after_days=settings.decay_after_days,
            decay_factor=settings.decay_factor,
            min_confidence=settings.min_confidence,
        )
