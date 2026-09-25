"""Tests for the shared OpenAI-compatible LLM client helpers."""

from __future__ import annotations

import pytest

from shared.config import Settings
from shared.llm import LLMClient, LLMError, build_llm_client, extract_json_object


def test_extract_json_object_plain() -> None:
    assert extract_json_object('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_extract_json_object_fenced() -> None:
    assert extract_json_object('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_object_with_prose_and_nesting() -> None:
    text = 'Sure, here it is: {"a": {"b": 2}, "c": [1, 2]} — hope that helps'
    assert extract_json_object(text) == {"a": {"b": 2}, "c": [1, 2]}


def test_extract_json_object_skips_invalid_then_valid() -> None:
    text = '{not json} then {"ok": true}'
    assert extract_json_object(text) == {"ok": True}


def test_extract_json_object_raises_without_object() -> None:
    with pytest.raises(LLMError):
        extract_json_object("no json here")


def test_build_llm_client_returns_none_without_key() -> None:
    assert build_llm_client(Settings(llm_provider="none")) is None
    assert build_llm_client(Settings(llm_provider="openai", llm_api_key=None)) is None


def test_build_llm_client_uses_settings() -> None:
    client = build_llm_client(
        Settings(
            llm_provider="openai",
            llm_api_key="sk-test",
            llm_base_url="https://api.relaymodels.com/v1",
            llm_model="deepseek-v4-flash",
        )
    )
    assert isinstance(client, LLMClient)
    assert client.model == "deepseek-v4-flash"
    assert client.base_url == "https://api.relaymodels.com/v1"
