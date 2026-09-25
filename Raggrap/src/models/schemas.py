"""Pydantic models for data validation."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class SeverityLevel(StrEnum):
    """Mistake severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _utcnow() -> datetime:
    """Timezone-aware current UTC timestamp (replaces deprecated ``utcnow``)."""
    return datetime.now(UTC)


class Concept(BaseModel):
    """Represents a concept or entity in the knowledge graph."""

    name: str = Field(..., description="Name of the concept")
    type: str = Field(
        default="general", description="Type of concept (e.g., City, Country, Technology)"
    )
    description: str | None = Field(None, description="Description of the concept")


class Mistake(BaseModel):
    """Represents a mistake made by the AI."""

    concept: str = Field(..., description="Main concept related to the mistake")
    description: str = Field(..., description="Description of what went wrong")
    rule: str = Field(..., description="Correction rule or correct information")
    severity: SeverityLevel = Field(
        default=SeverityLevel.MEDIUM, description="Severity of the mistake"
    )
    query: str | None = Field(None, description="Original query that triggered the mistake")
    wrong_answer: str | None = Field(None, description="The incorrect answer that was given")
    correct_answer: str | None = Field(None, description="The correct answer")
    query_pattern: str | None = Field(
        None, description="Pattern of queries that trigger this mistake"
    )
    timestamp: datetime = Field(
        default_factory=_utcnow, description="When the mistake was recorded"
    )


class Rule(BaseModel):
    """Represents a correction rule."""

    id: str = Field(..., description="Unique identifier for the rule")
    text: str = Field(..., description="The correction rule text")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Confidence score of the rule"
    )
    applies_to: list[str] = Field(default_factory=list, description="Concepts this rule applies to")
    created_at: datetime = Field(default_factory=_utcnow)


class QueryPattern(BaseModel):
    """Represents a pattern of user queries linked to recorded mistakes."""

    text: str = Field(..., description="Normalised query pattern text")
    mistake_ids: list[str] = Field(
        default_factory=list, description="Mistakes triggered by this pattern"
    )
    created_at: datetime = Field(default_factory=_utcnow)


class QueryRequest(BaseModel):
    """Request model for the query endpoint."""

    query: str = Field(..., min_length=1, description="User query")
    use_cache: bool = Field(default=True, description="Whether to use cached responses")
    include_explanation: bool = Field(default=False, description="Include reasoning in response")


class QueryResponse(BaseModel):
    """Response model for the query endpoint."""

    query: str
    answer: str
    warnings_applied: list[str] = Field(
        default_factory=list, description="Warnings from past mistakes"
    )
    was_corrected: bool = Field(
        default=False, description="Whether the initial response was corrected"
    )
    cached: bool = Field(default=False, description="Whether response came from cache")
    timestamp: datetime = Field(default_factory=_utcnow)
    reasoning: str | None = Field(None, description="Explanation of the reasoning process")


class EvaluationResult(BaseModel):
    """Result of response evaluation."""

    is_correct: bool = Field(..., description="Whether the response is correct")
    reason: str = Field(..., description="Explanation of the evaluation")
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Confidence in the evaluation"
    )


class MistakeRecord(BaseModel):
    """Complete record of a mistake with metadata."""

    mistake_id: str
    concept: str
    description: str
    rule: str
    severity: SeverityLevel
    query: str | None = None
    wrong_answer: str | None = None
    correct_answer: str | None = None
    query_pattern: str | None = None
    timestamp: datetime
    corrected_count: int = Field(
        default=0, description="Number of times this rule has been applied"
    )


class HealthResponse(BaseModel):
    status: str
    graph_store: str
    vector_store: str
    cache_store: str
    llm_provider: str


class StatisticsResponse(BaseModel):
    total_concepts: int
    total_mistakes: int
    total_rules: int
    avg_rule_applications: float
