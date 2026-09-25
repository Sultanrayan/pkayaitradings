"""News ingestion from biquote's aggregated news endpoints."""

from __future__ import annotations

from data_pipeline.biquote_client import BiquoteClient
from shared.schemas.market import NewsArticle


class BiquoteNewsSource:
    """Fetches symbol-specific and broad market news.

    Args:
        client: The shared biquote REST client.
    """

    def __init__(self, client: BiquoteClient) -> None:
        self._client = client

    async def fetch_symbol_news(
        self, symbol: str, *, limit: int = 10, language: str = "en", country: str = "US"
    ) -> list[NewsArticle]:
        """Return news filtered by ``symbol``."""
        return await self._client.get_news(
            symbol=symbol, language=language, country=country, max_results=limit
        )

    async def fetch_market_news(
        self, *, limit: int = 10, language: str = "en", country: str = "US"
    ) -> list[NewsArticle]:
        """Return broad market news."""
        return await self._client.get_news(language=language, country=country, max_results=limit)

    async def fetch_hacker_news(
        self, *, query: str | None = None, limit: int = 5
    ) -> list[NewsArticle]:
        """Return Hacker News stories relevant to the query."""
        return await self._client.get_hacker_news(query=query, max_results=limit)
