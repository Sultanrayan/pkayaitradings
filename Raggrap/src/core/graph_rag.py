"""Core GraphRAG self-improvement engine."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from ...config.settings import Settings, settings
from ..models.schemas import EvaluationResult, Mistake, QueryResponse, SeverityLevel
from .cache_store import CacheStore, create_cache_store
from .entity_extractor import EntityExtractor
from .graph_store import GraphStore, create_graph_store
from .llm import LLMProvider, create_llm_provider
from .vector_store import VectorStore, create_vector_store

logger = logging.getLogger(__name__)


class GraphRAGEngine:
    """Answers queries while using recorded corrections as retrieval guardrails."""

    def __init__(
        self,
        config: Settings | None = None,
        *,
        graph_store: GraphStore | None = None,
        vector_store: VectorStore | None = None,
        cache_store: CacheStore | None = None,
        main_llm: LLMProvider | None = None,
        critic_llm: LLMProvider | None = None,
        entity_extractor: EntityExtractor | None = None,
    ) -> None:
        self.config = config or settings
        self.graph_store = graph_store or create_graph_store(self.config)
        self.vector_store = vector_store or create_vector_store(self.config)
        self.cache = cache_store or create_cache_store(self.config)
        self.main_llm = main_llm or create_llm_provider(self.config, self.config.main_llm_model)
        self.critic_llm = critic_llm or create_llm_provider(
            self.config, self.config.critic_llm_model, critic=True
        )
        self.entity_extractor = entity_extractor or EntityExtractor(self.config.spacy_model)

    def _generate_mistake_id(self, mistake: Mistake) -> str:
        content = f"{mistake.concept}\0{mistake.description}\0{mistake.timestamp.isoformat()}"
        return f"mistake_{hashlib.sha256(content.encode()).hexdigest()[:16]}"

    def _generate_rule_id(self, rule_text: str) -> str:
        return f"rule_{hashlib.sha256(rule_text.strip().encode()).hexdigest()[:16]}"

    def _get_cache_key(self, query: str, include_reasoning: bool = False) -> str:
        content = json.dumps(
            {"query": query.strip(), "reasoning": include_reasoning}, sort_keys=True
        )
        return f"raggrap:query:{hashlib.sha256(content.encode()).hexdigest()}"

    @staticmethod
    def _query_pattern(query: str) -> str:
        """Normalise a query into a repeatable pattern key."""
        return " ".join(query.strip().casefold().split()) or "unknown"

    def record_mistake(self, mistake: Mistake) -> str:
        mistake_id = self._generate_mistake_id(mistake)
        rule_id = self._generate_rule_id(mistake.rule)
        recorded_id = self.graph_store.record_mistake(mistake, mistake_id, rule_id)
        try:
            self.vector_store.add_mistake(recorded_id, mistake)
        except Exception as exc:
            logger.warning("Vector indexing failed: %s", exc)
        return recorded_id

    def get_related_mistakes(self, query: str) -> list[dict[str, Any]]:
        entities = self.entity_extractor.extract(query)
        graph_matches = self.graph_store.get_related_mistakes(
            entities, self.config.max_related_mistakes
        )
        try:
            vector_matches = self.vector_store.search(query, self.config.max_related_mistakes)
        except Exception as exc:
            logger.warning("Vector retrieval failed: %s", exc)
            vector_matches = []

        seen: set[str] = set()
        merged: list[dict[str, Any]] = []
        for record in [*graph_matches, *vector_matches]:
            identifier = (
                record.get("mistake_id") or f"{record.get('concept')}:{record.get('mistake')}"
            )
            if identifier not in seen:
                seen.add(identifier)
                merged.append(record)
            if len(merged) == self.config.max_related_mistakes:
                break
        return merged

    def build_enhanced_prompt(self, query: str, mistakes: list[dict[str, Any]]) -> str:
        if not mistakes:
            warnings = "No specific warnings for this query."
        else:
            warnings = "\n".join(
                "- Recorded correction for {concept}: Avoid '{mistake}'. Correct approach: '{rule}'".format(
                    concept=mistake.get("concept", "this topic"),
                    mistake=mistake.get("mistake", mistake.get("description", "a prior error")),
                    rule=mistake["rule"],
                )
                for mistake in mistakes
            )
        return f"""You are a helpful AI assistant. Answer accurately and precisely.

=== CORRECTIONS FROM PAST MISTAKES ===
{warnings}
======================================

Question: {query}

Provide a clear, accurate answer:"""

    def evaluate_response(self, query: str, response: str) -> EvaluationResult:
        prompt = f"""Evaluate whether this answer is factually correct and appropriate.

Question: {query}
Answer: {response}

Return only JSON in this format:
{{"is_correct": true, "reason": "brief explanation", "confidence": 0.0}}"""
        try:
            content = self.critic_llm.generate(prompt).strip()
            if content.startswith("```"):
                content = content.split("```", 2)[1].removeprefix("json").strip()
            return EvaluationResult.model_validate_json(content)
        except Exception as exc:
            logger.warning("Response evaluation failed: %s", exc)
            return EvaluationResult(
                is_correct=True,
                reason="Critic unavailable; response was returned without automatic correction.",
                confidence=0.0,
            )

    def answer(
        self, query: str, use_cache: bool = True, include_reasoning: bool = False
    ) -> QueryResponse:
        query = query.strip()
        cache_key = self._get_cache_key(query, include_reasoning)
        if use_cache and self.config.enable_cache:
            try:
                cached_response = self.cache.get(cache_key)
                if cached_response:
                    return cached_response.model_copy(update={"cached": True})
            except Exception as exc:
                logger.warning("Cache read failed: %s", exc)

        mistakes = self.get_related_mistakes(query)
        prompt = self.build_enhanced_prompt(query, mistakes)
        original_answer = self.main_llm.generate(prompt)
        evaluation = self.evaluate_response(query, original_answer)
        response = original_answer
        was_corrected = False

        if not evaluation.is_correct:
            was_corrected = True
            correction_prompt = f"""The previous answer was incorrect because: {evaluation.reason}

Question: {query}
Previous answer: {original_answer}

Provide a factually accurate replacement answer only."""
            response = self.main_llm.generate(correction_prompt)
            concept = self.entity_extractor.extract(query)
            self.record_mistake(
                Mistake(
                    concept=concept[0] if concept else "unknown",
                    description=f"Incorrect answer to: {query[:200]}",
                    rule=evaluation.reason,
                    severity=SeverityLevel.MEDIUM,
                    query=query,
                    wrong_answer=original_answer,
                    correct_answer=response,
                    query_pattern=self._query_pattern(query),
                )
            )

        result = QueryResponse(
            query=query,
            answer=response,
            warnings_applied=[
                record.get("mistake", record.get("description", "")) for record in mistakes
            ],
            was_corrected=was_corrected,
            cached=False,
            reasoning=evaluation.reason if include_reasoning else None,
        )
        if self.config.enable_cache:
            try:
                self.cache.setex(cache_key, self.config.cache_ttl, result)
            except Exception as exc:
                logger.warning("Cache write failed: %s", exc)
        return result

    def get_mistakes(self, limit: int = 100) -> list[dict[str, Any]]:
        return self.graph_store.get_mistakes(limit)

    def get_statistics(self) -> dict[str, Any]:
        return self.graph_store.statistics()

    def clear_cache(self) -> None:
        self.cache.flush()

    def health_check(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "graph_store": type(self.graph_store).__name__,
            "vector_store": type(self.vector_store).__name__,
            "cache_store": type(self.cache).__name__,
            "llm_provider": type(self.main_llm).__name__,
        }

    def close(self) -> None:
        self.graph_store.close()
        self.cache.close()

    def __enter__(self) -> GraphRAGEngine:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
