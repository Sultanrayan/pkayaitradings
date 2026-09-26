"""Community backend: posts, comments, follows, likes and notifications.

Provides a real, persistent backend for the frontend Community page. Data
lives in a single JSON store (``DATA_DIR/community.json``) — the same pattern
as the user/access/billing stores — and is seeded on first boot so the UI has
content immediately. When a bearer token is present the requesting user is a
registered account; otherwise the shared guest identity is used (local dev).

All responses use the camelCase field names the frontend already expects.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from orchestrator.auth import decode_token
from shared.config import get_settings
from shared.logging import get_logger
from shared.persistence import read_json, write_json

__all__ = ["build_community_store", "router"]

_logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/community", tags=["community"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _gen(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


# --------------------------------------------------------------------------- #
# Wire models (camelCase, matching the frontend types)
# --------------------------------------------------------------------------- #

class SocialUser(BaseModel):
    id: str
    name: str
    handle: str
    avatar: str | None = None
    bio: str = ""
    verified: bool = False
    followers: int = 0
    following: int = 0
    joinedAt: str


class PostAttachment(BaseModel):
    type: str
    id: str
    # image / video
    url: str | None = None
    alt: str | None = None
    # market / chart
    symbol: str | None = None
    timeframe: str | None = None
    # signal
    side: str | None = None
    entry: float | None = None
    target: float | None = None
    stop: float | None = None
    createdAt: str | None = None


class SocialPost(BaseModel):
    id: str
    authorId: str
    text: str
    attachments: list[PostAttachment] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    createdAt: str
    engagement: int = 0
    likes: int = 0
    likedByMe: bool = False
    reposts: int = 0
    repostedByMe: bool = False
    quotes: int = 0
    bookmarks: int = 0
    bookmarkedByMe: bool = False
    savedByMe: bool = False
    mutedByMe: bool = False
    blockedByMe: bool = False


class SocialComment(BaseModel):
    id: str
    postId: str
    parentId: str | None = None
    authorId: str
    text: str
    createdAt: str
    likes: int = 0
    likedByMe: bool = False
    reposts: int = 0
    repostedByMe: bool = False
    reportedByMe: bool = False
    deletedByAuthor: bool = False


class SocialNotification(BaseModel):
    id: str
    type: str
    actorId: str
    postId: str | None = None
    text: str
    createdAt: str
    read: bool = False


class SuggestedTrader(BaseModel):
    id: str
    name: str
    handle: str
    avatar: str | None = None
    bio: str = ""


class TrendingMarket(BaseModel):
    symbol: str
    posts: int
    deltaPct: float


class TrendingTopic(BaseModel):
    title: str
    posts: int


class SearchResults(BaseModel):
    users: list[SocialUser]
    posts: list[SocialPost]
    markets: list[str]
    hashtags: list[str]
    topics: list[str]


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #

class CreatePostRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    attachments: list[PostAttachment] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)


class AddCommentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    parentId: str | None = None


# --------------------------------------------------------------------------- #
# Store
# --------------------------------------------------------------------------- #

def _seed_days(days: int, hours: int = 0) -> str:
    return (_utcnow() - timedelta(days=days, hours=hours)).isoformat()


_AVATARS = [
    "/agents/technical_analyst.jpg",
    "/agents/news_monitor.jpg",
    "/agents/risk_manager.jpg",
    "/agents/decision_maker.jpg",
    "/logo-pkay.jpg",
]


def _seed_users() -> list[dict[str, Any]]:
    return [
        {
            "id": "u-goldfox",
            "name": "GoldFox",
            "handle": "goldfox",
            "avatar": _AVATARS[0],
            "bio": "XAU trader · Daily charts · Always respect the stop.",
            "verified": True,
            "followers": 1240,
            "following": 180,
            "joinedAt": _seed_days(420),
        },
        {
            "id": "u-macrotrader",
            "name": "Macro Trader",
            "handle": "macrotrader",
            "avatar": _AVATARS[1],
            "bio": "Macro events, central banks and USD. Views not advice.",
            "verified": True,
            "followers": 2890,
            "following": 96,
            "joinedAt": _seed_days(700),
        },
        {
            "id": "u-btcstacker",
            "name": "BTC Stacker",
            "handle": "btcstacker",
            "avatar": _AVATARS[2],
            "bio": "Bitcoin & crypto structure. Risk-first since 2019.",
            "verified": False,
            "followers": 3580,
            "following": 210,
            "joinedAt": _seed_days(830),
        },
        {
            "id": "u-scalpqueen",
            "name": "Scalp Queen",
            "handle": "scalpqueen",
            "avatar": _AVATARS[3],
            "bio": "M15 scalps on indices. Journal every trade.",
            "verified": False,
            "followers": 940,
            "following": 140,
            "joinedAt": _seed_days(265),
        },
        {
            "id": "u-hedgehog",
            "name": "Hedgehog",
            "handle": "hedgehog",
            "avatar": _AVATARS[4],
            "bio": "Options, vol and patience.",
            "verified": True,
            "followers": 1720,
            "following": 310,
            "joinedAt": _seed_days(540),
        },
    ]


def _seed_posts() -> list[dict[str, Any]]:
    days = _seed_days
    return [
        {
            "id": "p-1",
            "authorId": "u-goldfox",
            "text": "Gold respect the $4,270 support again. Each touch here has produced a bounce — watch the M15 reclaim above $4,285 for longs.",
            "attachments": [
                {"type": "market", "id": "a-m1", "symbol": "XAUUSD"},
                {"type": "chart", "id": "a-m2", "symbol": "XAUUSD", "timeframe": "M15"},
            ],
            "hashtags": ["gold", "xauusd", "support"],
            "createdAt": days(0, 1),
            "engagement": 128,
            "likes": 46,
            "reposts": 12,
            "quotes": 3,
            "bookmarks": 8,
        },
        {
            "id": "p-2",
            "authorId": "u-btcstacker",
            "text": "Bitcoin inside the weekly range. The 96k level is the line in the sand — breaks above open the door to 98-101k. No position until a close.",
            "attachments": [
                {"type": "market", "id": "a-b1", "symbol": "BTCUSD"},
                {
                    "type": "signal",
                    "id": "a-b2",
                    "symbol": "BTCUSD",
                    "side": "BUY",
                    "timeframe": "H1",
                    "entry": 96600,
                    "target": 101200,
                    "stop": 95800,
                    "createdAt": days(0, 3),
                },
            ],
            "hashtags": ["bitcoin", "btcusd", "setup"],
            "createdAt": days(0, 3),
            "engagement": 212,
            "likes": 83,
            "reposts": 21,
            "quotes": 6,
            "bookmarks": 19,
        },
        {
            "id": "p-3",
            "authorId": "u-macrotrader",
            "text": "CPI recap: a firm core, but the market prefers to lean on the soft side. Expect the pair to stay range-bound into the press conference.",
            "attachments": [],
            "hashtags": ["macro", "fed", "cpi"],
            "createdAt": days(1, 2),
            "engagement": 340,
            "likes": 140,
            "reposts": 40,
            "quotes": 15,
            "bookmarks": 22,
        },
        {
            "id": "p-4",
            "authorId": "u-scalpqueen",
            "text": "US500 scalping model for the afternoon session. Backtest note: the edge is in the first 90 minutes after the open — patience after that.",
            "attachments": [
                {"type": "chart", "id": "a-s1", "symbol": "US500", "timeframe": "M15"},
            ],
            "hashtags": ["us500", "scalping"],
            "createdAt": days(1, 6),
            "engagement": 144,
            "likes": 52,
            "reposts": 14,
            "quotes": 4,
            "bookmarks": 25,
        },
        {
            "id": "p-5",
            "authorId": "u-hedgehog",
            "text": "Volatility crush into month-end. The VIX curve is pricing a quiet holiday week — sell premium with defined risk only.",
            "attachments": [],
            "hashtags": ["options", "vol", "vix"],
            "createdAt": days(2, 4),
            "engagement": 96,
            "likes": 31,
            "reposts": 9,
            "quotes": 2,
            "bookmarks": 11,
        },
        {
            "id": "p-6",
            "authorId": "u-goldfox",
            "text": "Weekly gold review: higher lows on H4, momentum oscillator curling up. If 4,300 clears we extend into the 4,320 measured move.",
            "attachments": [],
            "hashtags": ["gold", "xauusd", "review"],
            "createdAt": days(3, 5),
            "engagement": 175,
            "likes": 64,
            "reposts": 18,
            "quotes": 7,
            "bookmarks": 14,
        },
        {
            "id": "p-7",
            "authorId": "u-btcstacker",
            "text": "Funding reset on BTC. Perp funding back to neutral means the squeeze fuel is gone — range trading until the spot flow resumes.",
            "attachments": [],
            "hashtags": ["bitcoin", "funding", "flows"],
            "createdAt": days(4, 2),
            "engagement": 88,
            "likes": 27,
            "reposts": 8,
            "quotes": 1,
            "bookmarks": 6,
        },
        {
            "id": "p-8",
            "authorId": "u-macrotrader",
            "text": "EURUSD — the rate differential keeps crowding the corners of the box. A snap back to the mid-band is the higher probability path.",
            "attachments": [
                {"type": "market", "id": "a-e1", "symbol": "EURUSD"},
            ],
            "hashtags": ["fx", "eurusd", "macro"],
            "createdAt": days(5, 6),
            "engagement": 122,
            "likes": 41,
            "reposts": 13,
            "quotes": 5,
            "bookmarks": 9,
        },
        {
            "id": "p-9",
            "authorId": "u-scalpqueen",
            "text": "Journal: today was about saying no to the 14:00 chop. Only 2 losses, both small. The rules beat the emotion — write yours down.",
            "attachments": [],
            "hashtags": ["journal", "discipline"],
            "createdAt": days(6, 8),
            "engagement": 210,
            "likes": 96,
            "reposts": 30,
            "quotes": 12,
            "bookmarks": 33,
        },
        {
            "id": "p-10",
            "authorId": "u-hedgehog",
            "text": "New to the community? Introduce yourself — tell us what you trade, your timezone and one lesson the market taught you.",
            "attachments": [],
            "hashtags": ["community", "introduce"],
            "createdAt": days(7, 1),
            "engagement": 264,
            "likes": 110,
            "reposts": 22,
            "quotes": 19,
            "bookmarks": 5,
        },
    ]


def _seed_comments() -> list[dict[str, Any]]:
    days = _seed_days
    return [
        {
            "id": "c-1",
            "postId": "p-1",
            "parentId": None,
            "authorId": "u-macrotrader",
            "text": "Support zone aligns with the 50% retracement on D1 — agree with the bounce thesis.",
            "createdAt": days(0, 0),
            "likes": 12,
            "reposts": 0,
        },
        {
            "id": "c-2",
            "postId": "p-1",
            "parentId": None,
            "authorId": "u-btcstacker",
            "text": "Careful fading the squeeze — last three touches printed 30k+ moves first.",
            "createdAt": days(0, 0),
            "likes": 8,
            "reposts": 1,
        },
        {
            "id": "c-2-1",
            "postId": "p-1",
            "parentId": "c-2",
            "authorId": "u-goldfox",
            "text": "Fair point — that is why the trigger is a close above the level, not the touch.",
            "createdAt": days(0, 0),
            "likes": 5,
            "reposts": 0,
        },
        {
            "id": "c-3",
            "postId": "p-2",
            "parentId": None,
            "authorId": "u-goldfox",
            "text": "Adding to favorites. The 101k target is deep but the structure supports it.",
            "createdAt": days(0, 2),
            "likes": 5,
            "reposts": 0,
        },
        {
            "id": "c-4",
            "postId": "p-3",
            "parentId": None,
            "authorId": "u-hedgehog",
            "text": "The dot-plot skew is the real driver here. Range trade unless the floor breaks.",
            "createdAt": days(1, 0),
            "likes": 7,
            "reposts": 0,
        },
        {
            "id": "c-5",
            "postId": "p-1",
            "parentId": "c-1",
            "authorId": "u-scalpqueen",
            "text": "Agreed on the zone, but I want to see the M15 reclaim first.",
            "createdAt": days(0, 0),
            "likes": 3,
            "reposts": 0,
        },
    ]


def _seed_notifications() -> list[dict[str, Any]]:
    days = _seed_days
    return [
        {
            "id": "n-1",
            "type": "follow",
            "actorId": "u-goldfox",
            "text": "GoldFox started following you",
            "createdAt": days(0, 2),
            "read": False,
        },
        {
            "id": "n-2",
            "type": "like",
            "actorId": "u-btcstacker",
            "postId": "p-1",
            "text": "BTC Stacker liked your post",
            "createdAt": days(1, 0),
            "read": False,
        },
        {
            "id": "n-3",
            "type": "comment",
            "actorId": "u-scalpqueen",
            "postId": "p-1",
            "text": "Scalp Queen replied to your post",
            "createdAt": days(1, 4),
            "read": True,
        },
    ]


@dataclass
class CommunityStore:
    """JSON-persisted community store (in-memory when no ``path`` given)."""

    users: list[dict[str, Any]] = field(default_factory=_seed_users)
    posts: list[dict[str, Any]] = field(default_factory=_seed_posts)
    comments: list[dict[str, Any]] = field(default_factory=_seed_comments)
    notifications: list[dict[str, Any]] = field(default_factory=_seed_notifications)
    following: list[str] = field(default_factory=lambda: ["u-goldfox", "u-btcstacker"])
    muted_posts: list[str] = field(default_factory=list)
    blocked_posts: list[str] = field(default_factory=list)
    path: Path | None = None

    def __post_init__(self) -> None:
        if self.path is not None:
            self._load()

    # -- persistence ------------------------------------------------------- #
    def _load(self) -> None:
        if self.path is None:
            return
        raw = read_json(self.path)
        if not isinstance(raw, dict):
            return
        store_users = raw.get("users")
        store_posts = raw.get("posts")
        if isinstance(store_posts, list) and store_posts:
            self.posts = store_posts
        if isinstance(store_users, list) and store_users:
            self.users = store_users
        if isinstance(raw.get("comments"), list):
            self.comments = raw["comments"]
        if isinstance(raw.get("notifications"), list):
            self.notifications = raw["notifications"]
        if isinstance(raw.get("following"), list):
            self.following = raw["following"]
        if isinstance(raw.get("muted_posts"), list):
            self.muted_posts = raw["muted_posts"]
        if isinstance(raw.get("blocked_posts"), list):
            self.blocked_posts = raw["blocked_posts"]

    def _persist(self) -> None:
        if self.path is None:
            return
        write_json(
            self.path,
            {
                "users": self.users,
                "posts": self.posts,
                "comments": self.comments,
                "notifications": self.notifications,
                "following": self.following,
                "muted_posts": self.muted_posts,
                "blocked_posts": self.blocked_posts,
            },
        )

    def commit(self) -> None:
        self._persist()

    # -- helpers ---------------------------------------------------------- #
    def user(self, user_id: str) -> dict[str, Any] | None:
        return next((u for u in self.users if u["id"] == user_id), None)

    def post(self, post_id: str) -> dict[str, Any] | None:
        return next((p for p in self.posts if p["id"] == post_id), None)

    def comment(self, comment_id: str) -> dict[str, Any] | None:
        return next((c for c in self.comments if c["id"] == comment_id), None)

    def comments_for(self, post_id: str) -> list[dict[str, Any]]:
        return [c for c in self.comments if c["postId"] == post_id]

    def to_post(self, raw: dict[str, Any], me_id: str | None = None) -> SocialPost:
        me_id = me_id or "me"
        liked_by = raw.get("likedBy") or []
        reposted_by = raw.get("repostedBy") or []
        bookmarked_by = raw.get("bookmarkedBy") or []
        saved_by = raw.get("savedBy") or []
        return SocialPost(
            **raw,
            likedByMe=me_id in liked_by,
            repostedByMe=me_id in reposted_by,
            bookmarkedByMe=me_id in bookmarked_by,
            savedByMe=me_id in saved_by,
            mutedByMe=self.is_muted(raw["id"]),
            blockedByMe=self.is_blocked(raw["id"]),
        )

    def to_comment(self, raw: dict[str, Any], me_id: str | None = None) -> SocialComment:
        me_id = me_id or "me"
        liked_by = raw.get("likedBy") or []
        reposted_by = raw.get("repostedBy") or []
        reported_by = raw.get("reportedBy") or []
        return SocialComment(
            **raw,
            likedByMe=me_id in liked_by,
            repostedByMe=me_id in reposted_by,
            reportedByMe=me_id in reported_by,
        )

    def is_muted(self, post_id: str) -> bool:
        return post_id in self.muted_posts

    def is_blocked(self, post_id: str) -> bool:
        return post_id in self.blocked_posts

    def bump_engagement(self, post_id: str, delta: int) -> None:
        raw = self.post(post_id)
        if raw is not None:
            raw["engagement"] = int(raw.get("engagement", 0)) + delta

    def notifications_for(self, me_id: str | None = None) -> list[SocialNotification]:
        return [SocialNotification(**n) for n in self.notifications]

    def add_notification(self, *, ntype: str, actor_id: str, text: str, post_id: str | None = None) -> None:
        self.notifications.insert(
            0,
            {
                "id": _gen("n"),
                "type": ntype,
                "actorId": actor_id,
                "postId": post_id,
                "text": text,
                "createdAt": _utcnow().isoformat(),
                "read": False,
            },
        )

    # -- mutations -------------------------------------------------------- #
    def create_post(self, author_id: str, request: CreatePostRequest) -> SocialPost:
        raw = {
            "id": _gen("p"),
            "authorId": author_id,
            "text": request.text,
            "attachments": [a.model_dump() for a in request.attachments],
            "hashtags": list(request.hashtags),
            "createdAt": _utcnow().isoformat(),
            "engagement": 1,
            "likes": 0,
            "likedBy": [],
            "reposts": 0,
            "repostedBy": [],
            "quotes": 0,
            "bookmarks": 0,
            "bookmarkedBy": [],
            "savedBy": [],
        }
        self.posts.insert(0, raw)
        self.commit()
        return self.to_post(raw, author_id)

    def toggle_like(self, post_id: str, me_id: str) -> SocialPost:
        raw = self.post(post_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="Post not found")
        liked = raw.setdefault("likedBy", [])
        active = me_id in liked
        if active:
            liked.remove(me_id)
            raw["likes"] = int(raw.get("likes", 0)) - 1
            raw["engagement"] = int(raw.get("engagement", 0)) - 2
        else:
            liked.append(me_id)
            raw["likes"] = int(raw.get("likes", 0)) + 1
            raw["engagement"] = int(raw.get("engagement", 0)) + 2
        self.commit()
        return self.to_post(raw, me_id)

    def toggle_repost(self, post_id: str, me_id: str) -> SocialPost:
        raw = self.post(post_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="Post not found")
        reposted = raw.setdefault("repostedBy", [])
        active = me_id in reposted
        if active:
            reposted.remove(me_id)
            raw["reposts"] = int(raw.get("reposts", 0)) - 1
        else:
            reposted.append(me_id)
            raw["reposts"] = int(raw.get("reposts", 0)) + 1
        self.commit()
        return self.to_post(raw, me_id)

    def toggle_bookmark(self, post_id: str, me_id: str) -> SocialPost:
        raw = self.post(post_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="Post not found")
        bookmarked = raw.setdefault("bookmarkedBy", [])
        active = me_id in bookmarked
        if active:
            bookmarked.remove(me_id)
            raw["bookmarks"] = int(raw.get("bookmarks", 0)) - 1
        else:
            bookmarked.append(me_id)
            raw["bookmarks"] = int(raw.get("bookmarks", 0)) + 1
        self.commit()
        return self.to_post(raw, me_id)

    def toggle_save(self, post_id: str, me_id: str) -> SocialPost:
        raw = self.post(post_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="Post not found")
        saved = raw.setdefault("savedBy", [])
        if me_id in saved:
            saved.remove(me_id)
        else:
            saved.append(me_id)
        self.commit()
        return self.to_post(raw, me_id)

    def toggle_mute(self, post_id: str) -> SocialPost:
        raw = self.post(post_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="Post not found")
        if post_id in self.muted_posts:
            self.muted_posts.remove(post_id)
        else:
            self.muted_posts.append(post_id)
        self.commit()
        return self.to_post(raw)

    def block_post(self, post_id: str) -> SocialPost:
        raw = self.post(post_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="Post not found")
        if post_id not in self.blocked_posts:
            self.blocked_posts.append(post_id)
        if post_id in self.muted_posts:
            self.muted_posts.remove(post_id)
        self.commit()
        return self.to_post(raw)

    def add_comment(self, post_id: str, author_id: str, request: AddCommentRequest) -> SocialComment:
        if self.post(post_id) is None:
            raise HTTPException(status_code=404, detail="Post not found")
        parent = request.parentId
        if parent is not None and self.comment(parent) is None:
            raise HTTPException(status_code=404, detail="Parent comment not found")
        raw: dict[str, Any] = {
            "id": _gen("c"),
            "postId": post_id,
            "parentId": parent,
            "authorId": author_id,
            "text": request.text,
            "createdAt": _utcnow().isoformat(),
            "likes": 0,
            "likedBy": [],
            "reposts": 0,
            "repostedBy": [],
            "reportedBy": [],
            "deletedByAuthor": False,
        }
        self.comments.append(raw)
        author = self.user(author_id) or {"name": "Guest"}
        ntype = "reply" if parent else "comment"
        self.add_notification(
            ntype=ntype,
            actor_id=author_id,
            post_id=post_id,
            text=f"{author['name']} {('replied to a comment' if parent else 'commented on a post')}",
        )
        self.bump_engagement(post_id, 1)
        self.commit()
        return self.to_comment(raw, author_id)

    def toggle_comment_like(self, comment_id: str, me_id: str) -> SocialComment:
        raw = self.comment(comment_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        liked = raw.setdefault("likedBy", [])
        active = me_id in liked
        if active:
            liked.remove(me_id)
            raw["likes"] = int(raw.get("likes", 0)) - 1
        else:
            liked.append(me_id)
            raw["likes"] = int(raw.get("likes", 0)) + 1
        self.commit()
        return self.to_comment(raw, me_id)

    def toggle_comment_repost(self, comment_id: str, me_id: str) -> SocialComment:
        raw = self.comment(comment_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        reposted = raw.setdefault("repostedBy", [])
        active = me_id in reposted
        if active:
            reposted.remove(me_id)
            raw["reposts"] = int(raw.get("reposts", 0)) - 1
        else:
            reposted.append(me_id)
            raw["reposts"] = int(raw.get("reposts", 0)) + 1
        self.commit()
        return self.to_comment(raw, me_id)

    def delete_comment(self, comment_id: str, me_id: str) -> None:
        raw = self.comment(comment_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        if raw.get("authorId") != me_id:
            raise HTTPException(status_code=403, detail="You can only delete your own comments")
        raw["deletedByAuthor"] = True
        self.commit()

    def report_comment(self, comment_id: str, me_id: str) -> SocialComment:
        raw = self.comment(comment_id)
        if raw is None:
            raise HTTPException(status_code=404, detail="Comment not found")
        reported = raw.setdefault("reportedBy", [])
        if me_id not in reported:
            reported.append(me_id)
        self.commit()
        return self.to_comment(raw, me_id)

    def follow(self, user_id: str) -> None:
        if user_id not in self.following:
            self.following.append(user_id)
            target = self.user(user_id)
            if target is not None:
                target["followers"] = int(target.get("followers", 0)) + 1
            self.add_notification(
                ntype="follow",
                actor_id="me",
                text=f"You followed {target['name'] if target else 'a trader'}",
            )
            self.commit()

    def unfollow(self, user_id: str) -> None:
        if user_id in self.following:
            self.following.remove(user_id)
            target = self.user(user_id)
            if target is not None:
                target["followers"] = max(0, int(target.get("followers", 0)) - 1)
            self.commit()

    def mark_all_read(self) -> int:
        count = sum(1 for n in self.notifications if not n.get("read"))
        for n in self.notifications:
            n["read"] = True
        self.commit()
        return count


# --------------------------------------------------------------------------- #
# Dependency helpers
# --------------------------------------------------------------------------- #

# Module-level singleton so every request shares the same in-memory store.
_COMMUNITY_STORE = None


def get_store() -> CommunityStore:
    global _COMMUNITY_STORE
    if _COMMUNITY_STORE is None:
        _COMMUNITY_STORE = build_community_store()
    return _COMMUNITY_STORE


def _me_id(request: Any) -> str:
    """Resolve the acting user id (auth token → account, else local guest)."""
    if request is None:
        return "me"
    headers = getattr(request, "headers", None)
    if headers is None:
        return "me"
    header = headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if not token:
        return "me"
    try:
        payload = decode_token(token, get_settings().auth_secret)
    except Exception:
        return "me"
    return str(payload.get("sub") or "me")


store_dep = Depends(get_store)


def build_community_store() -> CommunityStore:
    """Build the store, persisting to `DATA_DIR/community.json` when set."""
    data_dir = get_settings().data_dir
    path = Path(data_dir) / "community.json" if data_dir else None
    store = CommunityStore(path=path)
    if data_dir and path is not None and not path.exists():
        store.commit()
    return store


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #

@router.get("/feed", response_model=list[SocialPost])
def feed(
    store: CommunityStore = store_dep,
    tab: str = Query("forYou", pattern="^(forYou|following|trending)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(6, ge=1, le=50),
    request: Any = None,
) -> list[SocialPost]:
    me_id = _me_id(request)
    candidates = [p for p in store.posts if not store.is_blocked(p["id"])]
    if tab == "following":
        candidates = [p for p in candidates if p["authorId"] in store.following]
        ordered = sorted(
            candidates,
            key=lambda p: p.get("createdAt", ""),
            reverse=True,
        )
    elif tab == "trending":
        candidates = [p for p in candidates if p.get("engagement", 0) > 40]
        ordered = sorted(candidates, key=lambda p: p.get("engagement", 0), reverse=True)
    else:
        ordered = sorted(candidates, key=lambda p: p.get("createdAt", ""), reverse=True)
    return [store.to_post(p, me_id) for p in ordered[(page - 1) * page_size : page * page_size]]


@router.get("/posts/{post_id}", response_model=SocialPost)
def get_post(post_id: str, store: CommunityStore = store_dep, request: Any = None) -> SocialPost:
    raw = store.post(post_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return store.to_post(raw, _me_id(request))


@router.post("/posts", response_model=SocialPost, status_code=status.HTTP_201_CREATED)
def create_post(
    body: CreatePostRequest,
    store: CommunityStore = store_dep,
    request: Any = None,
) -> SocialPost:
    return store.create_post(_me_id(request), body)


@router.post("/posts/{post_id}/like", response_model=SocialPost)
def like_post(post_id: str, store: CommunityStore = store_dep, request: Any = None) -> SocialPost:
    return store.toggle_like(post_id, _me_id(request))


@router.post("/posts/{post_id}/repost", response_model=SocialPost)
def repost(post_id: str, store: CommunityStore = store_dep, request: Any = None) -> SocialPost:
    return store.toggle_repost(post_id, _me_id(request))


@router.post("/posts/{post_id}/bookmark", response_model=SocialPost)
def bookmark_post(post_id: str, store: CommunityStore = store_dep, request: Any = None) -> SocialPost:
    return store.toggle_bookmark(post_id, _me_id(request))


@router.post("/posts/{post_id}/save", response_model=SocialPost)
def save_post(post_id: str, store: CommunityStore = store_dep, request: Any = None) -> SocialPost:
    return store.toggle_save(post_id, _me_id(request))


@router.post("/posts/{post_id}/mute", response_model=SocialPost)
def mute_post(post_id: str, store: CommunityStore = store_dep, request: Any = None) -> SocialPost:
    return store.toggle_mute(post_id)


@router.post("/posts/{post_id}/block", response_model=SocialPost)
def block_post(post_id: str, store: CommunityStore = store_dep, request: Any = None) -> SocialPost:
    return store.block_post(post_id)


@router.get("/posts/{post_id}/comments", response_model=list[SocialComment])
def get_comments(post_id: str, store: CommunityStore = store_dep, request: Any = None) -> list[SocialComment]:
    me_id = _me_id(request)
    return [store.to_comment(c, me_id) for c in store.comments_for(post_id)]


@router.post("/posts/{post_id}/comments", response_model=SocialComment, status_code=status.HTTP_201_CREATED)
def add_comment(
    post_id: str,
    body: AddCommentRequest,
    store: CommunityStore = store_dep,
    request: Any = None,
) -> SocialComment:
    return store.add_comment(post_id, _me_id(request), body)


@router.post("/comments/{comment_id}/like", response_model=SocialComment)
def like_comment(comment_id: str, store: CommunityStore = store_dep, request: Any = None) -> SocialComment:
    return store.toggle_comment_like(comment_id, _me_id(request))


@router.post("/comments/{comment_id}/repost", response_model=SocialComment)
def repost_comment(comment_id: str, store: CommunityStore = store_dep, request: Any = None) -> SocialComment:
    return store.toggle_comment_repost(comment_id, _me_id(request))


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(comment_id: str, store: CommunityStore = store_dep, request: Any = None) -> None:
    store.delete_comment(comment_id, _me_id(request))


@router.post("/comments/{comment_id}/report", response_model=SocialComment)
def report_comment(comment_id: str, store: CommunityStore = store_dep, request: Any = None) -> SocialComment:
    return store.report_comment(comment_id, _me_id(request))


@router.get("/users", response_model=list[SocialUser])
def list_users(store: CommunityStore = store_dep) -> list[SocialUser]:
    return [SocialUser(**u) for u in store.users]


@router.get("/users/{user_id}", response_model=SocialUser)
def get_user(user_id: str, store: CommunityStore = store_dep) -> SocialUser:
    raw = store.user(user_id)
    if raw is None:
        raise HTTPException(status_code=404, detail="User not found")
    return SocialUser(**raw)


@router.post("/users/{user_id}/follow")
def follow_user(user_id: str, store: CommunityStore = store_dep) -> dict[str, bool]:
    if store.user(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    store.follow(user_id)
    return {"following": user_id in store.following}


@router.delete("/users/{user_id}/follow")
def unfollow_user(user_id: str, store: CommunityStore = store_dep) -> dict[str, bool]:
    if store.user(user_id) is None:
        raise HTTPException(status_code=404, detail="User not found")
    store.unfollow(user_id)
    return {"following": user_id in store.following}


@router.get("/notifications", response_model=list[SocialNotification])
def get_notifications(store: CommunityStore = store_dep) -> list[SocialNotification]:
    return store.notifications_for()


@router.post("/notifications/read")
def mark_notifications_read(store: CommunityStore = store_dep) -> dict[str, int]:
    return {"mark": store.mark_all_read()}


@router.get("/search", response_model=SearchResults)
def search(
    store: CommunityStore = store_dep,
    q: str = Query(min_length=1, max_length=120),
    request: Any = None,
) -> SearchResults:
    needle = q.lower()
    me_id = _me_id(request)
    users = [SocialUser(**u) for u in store.users if needle in u["name"].lower() or needle in u["handle"].lower()]
    posts = [store.to_post(p, me_id) for p in store.posts if needle in p.get("text", "").lower()]
    markets: list[str] = []
    hashtags: list[str] = []
    for p in store.posts:
        for a in p.get("attachments", []):
            if a.get("type") in {"market", "chart"} and a.get("symbol"):
                symbol = a["symbol"]
                if needle in symbol.lower() and symbol not in markets:
                    markets.append(symbol)
        for h in p.get("hashtags", []):
            if needle in f"#{h}".lower() and h not in hashtags:
                hashtags.append(h)
    topics = [t for t in ("Gold breakout", "BTC resistance", "Market outlook", "Macro events", "Options vol") if needle in t.lower()]
    return SearchResults(users=users, posts=posts, markets=markets, hashtags=hashtags, topics=topics)


@router.get("/trending")
def trending(store: CommunityStore = store_dep) -> dict[str, Any]:
    return {
        "markets": [
            {"symbol": "XAUUSD", "posts": 214, "deltaPct": 0.42},
            {"symbol": "BTCUSD", "posts": 189, "deltaPct": -1.1},
            {"symbol": "EURUSD", "posts": 96, "deltaPct": 0.08},
            {"symbol": "US500", "posts": 88, "deltaPct": 0.31},
        ],
        "topics": [
            {"title": "Gold breakout", "posts": 214},
            {"title": "BTC resistance", "posts": 189},
            {"title": "Market outlook", "posts": 156},
            {"title": "Macro events", "posts": 121},
            {"title": "Options vol", "posts": 74},
        ],
        "suggested": [
            {"id": u["id"], "name": u["name"], "handle": u["handle"], "avatar": u.get("avatar"), "bio": u.get("bio", "")}
            for u in store.users
            if u["id"] not in store.following
        ],
    }
