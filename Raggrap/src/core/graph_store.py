"""Graph storage adapters for correction knowledge.

Schema follows the research doc:
- ``Concept`` -- topic/entity
- ``Mistake``  -- error instance
- ``Rule``     -- correction logic
- ``QueryPattern`` -- user input pattern

Edges: ``HAS_MISCONCEPTION`` (Concept->Mistake), ``CORRECTED_BY``
(Mistake->Rule), ``APPLIES_TO`` (Rule->Concept), ``TRIGGERED``
(QueryPattern->Mistake).
"""

from __future__ import annotations

from typing import Any, Protocol

from ..models.schemas import Mistake


class GraphStore(Protocol):
    """Common interface for graph stores."""

    def record_mistake(self, mistake: Mistake, mistake_id: str, rule_id: str) -> str: ...

    def record_query_pattern(self, pattern: str, mistake_id: str) -> None: ...

    def get_related_mistakes(self, entities: list[str], limit: int) -> list[dict[str, Any]]: ...

    def get_mistakes(self, limit: int = 100) -> list[dict[str, Any]]: ...

    def statistics(self) -> dict[str, Any]: ...

    def close(self) -> None: ...


class InMemoryGraphStore:
    """Process-local graph store (no external dependencies)."""

    def __init__(self) -> None:
        self._mistakes: dict[str, dict[str, Any]] = {}
        self._rules: dict[str, dict[str, Any]] = {}
        self._concepts: set[str] = set()
        # pattern text -> set of mistake ids it has triggered
        self._patterns: dict[str, set[str]] = {}

    def record_mistake(self, mistake: Mistake, mistake_id: str, rule_id: str) -> str:
        concept = mistake.concept.strip()
        self._concepts.add(concept.casefold())
        rule = self._rules.setdefault(
            rule_id,
            {"id": rule_id, "text": mistake.rule, "applied_count": 0},
        )
        rule["applied_count"] += 1
        self._mistakes[mistake_id] = {
            "mistake_id": mistake_id,
            "concept": concept,
            "mistake": mistake.description,
            "description": mistake.description,
            "rule": rule["text"],
            "rule_id": rule_id,
            "severity": mistake.severity.value,
            "query": mistake.query,
            "wrong_answer": mistake.wrong_answer,
            "correct_answer": mistake.correct_answer,
            "query_pattern": mistake.query_pattern,
            "timestamp": mistake.timestamp,
        }
        if mistake.query_pattern:
            self.record_query_pattern(mistake.query_pattern, mistake_id)
        return mistake_id

    def record_query_pattern(self, pattern: str, mistake_id: str) -> None:
        key = pattern.strip().casefold()
        if key:
            self._patterns.setdefault(key, set()).add(mistake_id)

    def get_related_mistakes(self, entities: list[str], limit: int) -> list[dict[str, Any]]:
        normalized = {entity.casefold().strip() for entity in entities if entity.strip()}
        matches = [
            record
            for record in self._mistakes.values()
            if record["concept"].casefold() in normalized
            or any(record["concept"].casefold() in entity for entity in normalized)
            or any(entity in record["concept"].casefold() for entity in normalized)
        ]
        severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        return sorted(matches, key=lambda item: severity_rank[item["severity"]], reverse=True)[
            :limit
        ]

    def get_mistakes(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._mistakes.values())[-limit:]

    def statistics(self) -> dict[str, Any]:
        applications = [rule["applied_count"] for rule in self._rules.values()]
        return {
            "total_concepts": len(self._concepts),
            "total_mistakes": len(self._mistakes),
            "total_rules": len(self._rules),
            "avg_rule_applications": round(sum(applications) / len(applications), 2)
            if applications
            else 0,
        }

    def close(self) -> None:
        pass


class Neo4jGraphStore:
    """Neo4j-backed graph store (falls back to in-memory when unavailable)."""

    def __init__(self, driver: Any) -> None:
        self._driver = driver
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        constraints = [
            "CREATE CONSTRAINT concept_name IF NOT EXISTS FOR (c:Concept) REQUIRE c.name IS UNIQUE",
            "CREATE CONSTRAINT mistake_id IF NOT EXISTS FOR (m:Mistake) REQUIRE m.id IS UNIQUE",
            "CREATE CONSTRAINT rule_id IF NOT EXISTS FOR (r:Rule) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT pattern_text IF NOT EXISTS FOR (p:QueryPattern) REQUIRE p.text IS UNIQUE",
        ]
        with self._driver.session() as session:
            for constraint in constraints:
                session.run(constraint)

    def record_mistake(self, mistake: Mistake, mistake_id: str, rule_id: str) -> str:
        cypher = """
        MERGE (c:Concept {name: $concept})
        ON CREATE SET c.type = 'general', c.created_at = datetime()
        CREATE (m:Mistake {
            id: $mistake_id, description: $description, severity: $severity,
            query: $query, wrong_answer: $wrong_answer, correct_answer: $correct_answer,
            query_pattern: $query_pattern, timestamp: datetime($timestamp)
        })
        MERGE (r:Rule {id: $rule_id})
        ON CREATE SET r.text = $rule, r.confidence = 1.0, r.created_at = datetime(), r.applied_count = 1
        ON MATCH SET r.applied_count = coalesce(r.applied_count, 0) + 1
        CREATE (c)-[:HAS_MISCONCEPTION]->(m)
        CREATE (m)-[:CORRECTED_BY]->(r)
        MERGE (r)-[:APPLIES_TO]->(c)
        RETURN m.id AS mistake_id
        """
        with self._driver.session() as session:
            result = session.run(
                cypher,
                concept=mistake.concept,
                mistake_id=mistake_id,
                description=mistake.description,
                severity=mistake.severity.value,
                query=mistake.query,
                wrong_answer=mistake.wrong_answer,
                correct_answer=mistake.correct_answer,
                query_pattern=mistake.query_pattern,
                timestamp=mistake.timestamp.isoformat(),
                rule_id=rule_id,
                rule=mistake.rule,
            )
            record = result.single()
        if mistake.query_pattern:
            self.record_query_pattern(mistake.query_pattern, mistake_id)
        return record["mistake_id"] if record else mistake_id

    def record_query_pattern(self, pattern: str, mistake_id: str) -> None:
        cypher = """
        MERGE (p:QueryPattern {text: $pattern})
        MERGE (m:Mistake {id: $mistake_id})
        MERGE (p)-[:TRIGGERED]->(m)
        """
        with self._driver.session() as session:
            session.run(cypher, pattern=pattern.strip().casefold(), mistake_id=mistake_id)

    def get_related_mistakes(self, entities: list[str], limit: int) -> list[dict[str, Any]]:
        cypher = """
        MATCH (c:Concept)-[:HAS_MISCONCEPTION]->(m:Mistake)-[:CORRECTED_BY]->(r:Rule)
        WHERE toLower(c.name) IN $entities
        RETURN m.id AS mistake_id, m.description AS mistake, r.text AS rule,
               m.severity AS severity, c.name AS concept, m.query AS query,
               m.wrong_answer AS wrong_answer, m.correct_answer AS correct_answer,
               m.query_pattern AS query_pattern, m.timestamp AS timestamp
        ORDER BY CASE m.severity
            WHEN 'critical' THEN 4 WHEN 'high' THEN 3 WHEN 'medium' THEN 2 ELSE 1 END DESC
        LIMIT $limit
        """
        with self._driver.session() as session:
            return [
                record.data()
                for record in session.run(
                    cypher,
                    entities=[entity.casefold() for entity in entities],
                    limit=limit,
                )
            ]

    def get_mistakes(self, limit: int = 100) -> list[dict[str, Any]]:
        cypher = """
        MATCH (c:Concept)-[:HAS_MISCONCEPTION]->(m:Mistake)-[:CORRECTED_BY]->(r:Rule)
        RETURN m.id AS mistake_id, c.name AS concept, m.description AS description,
               r.text AS rule, m.severity AS severity, m.query AS query,
               m.wrong_answer AS wrong_answer, m.correct_answer AS correct_answer,
               m.query_pattern AS query_pattern, m.timestamp AS timestamp,
               coalesce(r.applied_count, 0) AS corrected_count
        ORDER BY m.timestamp DESC LIMIT $limit
        """
        with self._driver.session() as session:
            return [record.data() for record in session.run(cypher, limit=limit)]

    def statistics(self) -> dict[str, Any]:
        cypher = """
        MATCH (c:Concept) WITH count(c) AS concepts
        MATCH (m:Mistake) WITH concepts, count(m) AS mistakes
        MATCH (r:Rule) WITH concepts, mistakes, count(r) AS rules
        OPTIONAL MATCH (:Mistake)-[:CORRECTED_BY]->(linked_rule:Rule)
        RETURN concepts, mistakes, rules, avg(coalesce(linked_rule.applied_count, 0)) AS avg_applications
        """
        with self._driver.session() as session:
            record = session.run(cypher).single()
        return {
            "total_concepts": record["concepts"] if record else 0,
            "total_mistakes": record["mistakes"] if record else 0,
            "total_rules": record["rules"] if record else 0,
            "avg_rule_applications": round(record["avg_applications"] or 0, 2) if record else 0,
        }

    def close(self) -> None:
        self._driver.close()


def create_graph_store(settings: Any) -> GraphStore:
    if not settings.neo4j_uri:
        return InMemoryGraphStore()
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=2,
        )
        driver.verify_connectivity()
        return Neo4jGraphStore(driver)
    except Exception:
        return InMemoryGraphStore()
