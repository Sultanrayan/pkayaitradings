"""Entity extraction with SpaCy and a dependency-free fallback."""

from __future__ import annotations

import contextlib
import re


class EntityExtractor:
    """Extract candidate entities/keywords from a user query.

    Uses SpaCy NER and noun-chunks when ``en_core_web_sm`` is installed; the
    regex fallback keeps the engine usable with no NLP dependencies.
    """

    def __init__(self, model_name: str) -> None:
        self._nlp = None
        with contextlib.suppress(Exception):
            import spacy

            self._nlp = spacy.load(model_name)

    def extract(self, query: str) -> list[str]:
        if self._nlp is not None:
            doc = self._nlp(query)
            entities = [entity.text.strip() for entity in doc.ents]
            with contextlib.suppress(Exception):
                entities.extend(chunk.text.strip() for chunk in doc.noun_chunks)
            entities = [entity for entity in entities if entity]
            if entities:
                return list(dict.fromkeys(entities))
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", query)
        phrases = re.findall(r"(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", query)
        return list(dict.fromkeys([*phrases, *words]))
