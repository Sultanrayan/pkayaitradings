"""Tests for the community backend (posts, comments, follows, feed, search)."""

from __future__ import annotations

import httpx
import pytest

from orchestrator.community import CommunityStore
from orchestrator.main import app


@pytest.mark.asyncio
async def test_api_feed_and_search() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        feed = await client.get("/api/v1/community/feed", params={"tab": "forYou"})
        assert feed.status_code == 200
        body = feed.json()
        assert isinstance(body, list)
        assert len(body) > 0
        assert "authorId" in body[0]

        search = await client.get("/api/v1/community/search", params={"q": "gold"})
        assert search.status_code == 200
        result = search.json()
        assert "posts" in result and "users" in result and "hashtags" in result

        trending = await client.get("/api/v1/community/trending")
        assert trending.status_code == 200
        payload = trending.json()
        assert "markets" in payload and "topics" in payload and "suggested" in payload


@pytest.mark.asyncio
async def test_api_comment_flow() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        post_id = "p-1"
        comments = await client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert comments.status_code == 200
        assert len(comments.json()) >= 1

        new = await client.post(
            f"/api/v1/community/posts/{post_id}/comments",
            json={"text": "Backend test comment"},
        )
        assert new.status_code == 201
        comment_id = new.json()["id"]

        like = await client.post(f"/api/v1/community/comments/{comment_id}/like")
        assert like.status_code == 200
        assert like.json()["likedByMe"] is True

        delete = await client.delete(f"/api/v1/community/comments/{comment_id}")
        assert delete.status_code == 204


def test_store_persists_to_disk(tmp_path) -> None:
    from orchestrator.community import CreatePostRequest

    store = CommunityStore(path=tmp_path / "community.json")
    store.create_post("me", CreatePostRequest(text="Persisted post"))
    # reload from disk
    reloaded = CommunityStore(path=tmp_path / "community.json")
    assert len(reloaded.posts) == len(store.posts)