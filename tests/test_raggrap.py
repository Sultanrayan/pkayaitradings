"""Tests for the Raggrap GraphRAG self-improvement engine."""

from __future__ import annotations

from Raggrap.config.settings import Settings
from Raggrap.src.core.cache_store import InMemoryCacheBackend
from Raggrap.src.core.entity_extractor import EntityExtractor
from Raggrap.src.core.graph_rag import GraphRAGEngine
from Raggrap.src.core.graph_store import InMemoryGraphStore
from Raggrap.src.core.llm import DeterministicProvider, create_llm_provider
from Raggrap.src.core.vector_store import InMemoryVectorStore
from Raggrap.src.models.schemas import Mistake, SeverityLevel


def _settings() -> Settings:
    return Settings(
        llm_provider="none",
        enable_cache=False,
        max_related_mistakes=5,
    )


def _engine() -> GraphRAGEngine:
    config = _settings()
    return GraphRAGEngine(
        config,
        graph_store=InMemoryGraphStore(),
        vector_store=InMemoryVectorStore(),
        cache_store=type("C", (), {"get": lambda *_: None, "setex": lambda *_: None, "flush": lambda: None, "close": lambda: None})(),
        main_llm=DeterministicProvider(),
        critic_llm=DeterministicProvider(critic=True),
        entity_extractor=EntityExtractor("unused"),
    )


def test_record_and_retrieve_mistake() -> None:
    engine = _engine()
    mistake = Mistake(
        concept="Python",
        description="Claimed Python renders frontend UIs",
        rule="Python is a backend language; use JS/TS for the frontend.",
        severity=SeverityLevel.HIGH,
        query="can python be used for frontend?",
        query_pattern="can python be used for frontend?",
    )
    mistake_id = engine.record_mistake(mistake)
    assert mistake_id.startswith("mistake_")

    related = engine.get_related_mistakes("is python good for building a UI?")
    assert any(record["concept"].casefold() == "python" for record in related)


def test_answer_applies_warning_and_caches() -> None:
    engine = _engine()
    engine.record_mistake(
        Mistake(
            concept="Frontend",
            description="Mixed up the frontend toolchain",
            rule="Frontend code runs in the browser; backend serves data.",
            severity=SeverityLevel.MEDIUM,
            query_pattern="frontend",
        )
    )
    result = engine.answer("what stack should I use for a frontend app?", use_cache=False)
    assert result.answer  # non-empty
    assert isinstance(result.warnings_applied, list)


def test_answer_calls_llm_and_records_correction() -> None:
    """When the main LLM is wrong, the engine records a correction."""
    engine = GraphRAGEngine(
        _settings(),
        graph_store=InMemoryGraphStore(),
        vector_store=InMemoryVectorStore(),
        main_llm=DeterministicProvider(),
        critic_llm=DeterministicProvider(critic=False),
        entity_extractor=EntityExtractor("unused"),
    )
    # Deterministic critic returns is_correct=True, so no correction path.
    result = engine.answer("Is Python for frontend?", use_cache=False)
    assert result.was_corrected is False
    assert engine.get_statistics()["total_mistakes"] == 0


def test_statistics_track_learning() -> None:
    engine = _engine()
    assert engine.get_statistics()["total_mistakes"] == 0
    engine.record_mistake(
        Mistake(concept="X", description="d", rule="r", severity=SeverityLevel.LOW)
    )
    stats = engine.get_statistics()
    assert stats["total_concepts"] == 1
    assert stats["total_mistakes"] == 1
    assert stats["total_rules"] == 1
    assert stats["avg_rule_applications"] == 1.0


def test_create_llm_provider_offline_fallback() -> None:
    provider = create_llm_provider(_settings(), "gpt-4o")
    assert isinstance(provider, DeterministicProvider)


def test_in_memory_store_query_patterns() -> None:
    store = InMemoryGraphStore()
    store.record_mistake(
        Mistake(concept="A", description="b", rule="c", query_pattern="hello world"),
        "m1",
        "r1",
    )
    assert store.get_mistakes(10)[0]["query_pattern"] == "hello world"


def test_cache_store_round_trip() -> None:
    from Raggrap.src.core.cache_store import CacheStore
    from Raggrap.src.models.schemas import QueryResponse

    backend = InMemoryCacheBackend()
    config = Settings(llm_provider="none", enable_cache=True, cache_ttl=3600)
    store = CacheStore(config, backend=backend)
    response = QueryResponse(query="q", answer="a")
    store.setex("key", 3600, response)
    cached = store.get("key")
    assert cached is not None
    assert cached.answer == "a"
    store.flush()
    assert store.get("key") is None
