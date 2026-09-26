"use client";

import { useCallback, useSyncExternalStore } from "react";

/** Scalable social-community data layer.
 *
 * Seed content is deterministic; posts/comments/notifications/follows are then
 * persisted to localStorage so interactions survive reloads. The store exposes
 * a single `useSocial()` hook consumed by every Community component, with room
 * to swap the seed layer for a real API later.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type PostAttachment =
  | { type: "image"; id: string; url: string; alt?: string }
  | { type: "video"; id: string; url: string }
  | { type: "market"; id: string; symbol: string }
  | { type: "chart"; id: string; symbol: string; timeframe: string }
  | {
      type: "signal";
      id: string;
      symbol: string;
      side: "BUY" | "SELL";
      timeframe: string;
      entry: number;
      target: number;
      stop: number;
      createdAt: string;
    };

export interface SocialUser {
  id: string;
  name: string;
  handle: string;
  avatar: string | null;
  bio: string;
  verified: boolean;
  followers: number;
  following: number;
  joinedAt: string;
}

export interface SocialPost {
  id: string;
  authorId: string;
  text: string;
  attachments: PostAttachment[];
  hashtags: string[];
  createdAt: string;
  engagement: number;
  likes: number;
  likedByMe: boolean;
  reposts: number;
  repostedByMe: boolean;
  quotes: number;
  bookmarks: number;
  bookmarkedByMe: boolean;
  savedByMe: boolean;
  mutedByMe: boolean;
  blockedByMe: boolean;
}

export interface SocialComment {
  id: string;
  postId: string;
  parentId: string | null;
  authorId: string;
  text: string;
  createdAt: string;
  likes: number;
  likedByMe: boolean;
  reposts: number;
  repostedByMe: boolean;
  reportedByMe: boolean;
  deletedByAuthor: boolean;
}

export interface SocialNotification {
  id: string;
  type: "like" | "comment" | "reply" | "repost" | "follow" | "mention";
  actorId: string;
  postId?: string;
  text: string;
  createdAt: string;
  read: boolean;
}

export type FeedTab = "forYou" | "following" | "trending";

export interface SuggestedTrader {
  id: string;
  name: string;
  handle: string;
  avatar: string | null;
  bio: string;
}

export interface TrendingMarket {
  symbol: string;
  posts: number;
  deltaPct: number;
}

export interface TrendingTopic {
  title: string;
  posts: number;
}

// ---------------------------------------------------------------------------
// Seed data
// ---------------------------------------------------------------------------

const AVATARS = [
  "/agents/technical_analyst.jpg",
  "/agents/news_monitor.jpg",
  "/agents/risk_manager.jpg",
  "/agents/decision_maker.jpg",
  "/logo-pkay.jpg",
];

function daysAgo(days: number, hours = 0): string {
  return new Date(Date.now() - days * 86_400_000 - hours * 3_600_000).toISOString();
}

export const SEED_USERS: SocialUser[] = [
  {
    id: "u-goldfox",
    name: "GoldFox",
    handle: "goldfox",
    avatar: AVATARS[0],
    bio: "XAU trader · Daily charts · Always respect the stop.",
    verified: true,
    followers: 1240,
    following: 180,
    joinedAt: daysAgo(420),
  },
  {
    id: "u-macrotrader",
    name: "Macro Trader",
    handle: "macrotrader",
    avatar: AVATARS[1],
    bio: "Macro events, central banks and USD. Views not advice.",
    verified: true,
    followers: 2890,
    following: 96,
    joinedAt: daysAgo(700),
  },
  {
    id: "u-btcstacker",
    name: "BTC Stacker",
    handle: "btcstacker",
    avatar: AVATARS[2],
    bio: "Bitcoin & crypto structure. Risk-first since 2019.",
    verified: false,
    followers: 3580,
    following: 210,
    joinedAt: daysAgo(830),
  },
  {
    id: "u-scalpqueen",
    name: "Scalp Queen",
    handle: "scalpqueen",
    avatar: AVATARS[3],
    bio: "M15 scalps on indices. Journal every trade.",
    verified: false,
    followers: 940,
    following: 140,
    joinedAt: daysAgo(265),
  },
  {
    id: "u-hedgehog",
    name: "Hedgehog",
    handle: "hedgehog",
    avatar: AVATARS[4],
    bio: "Options, vol and patience.",
    verified: true,
    followers: 1720,
    following: 310,
    joinedAt: daysAgo(540),
  },
];

let postSerial = 0;
function pid(): string {
  postSerial += 1;
  return `p-${postSerial}`;
}
let aidSerial = 0;
function aid(): string {
  aidSerial += 1;
  return `a-${aidSerial}`;
}
let cidSerial = 0;
function cid(): string {
  cidSerial += 1;
  return `c-${cidSerial}`;
}

export function seedPosts(): SocialPost[] {
  return [
    {
      id: pid(),
      authorId: "u-goldfox",
      text: "Gold respect the $4,270 support again. Each touch here has produced a bounce — watch the M15 reclaim above $4,285 for longs.",
      attachments: [
        { type: "market", id: aid(), symbol: "XAUUSD" },
        { type: "chart", id: aid(), symbol: "XAUUSD", timeframe: "M15" },
      ],
      hashtags: ["gold", "xauusd", "support"],
      createdAt: daysAgo(0, 1),
      engagement: 128,
      likes: 46,
      likedByMe: false,
      reposts: 12,
      repostedByMe: false,
      quotes: 3,
      bookmarks: 8,
      bookmarkedByMe: false,
      savedByMe: false,
      mutedByMe: false,
      blockedByMe: false,
    },
    {
      id: pid(),
      authorId: "u-btcstacker",
      text: "Bitcoin inside the weekly range. The 96k level is the line in the sand — breaks above open the door to 98-101k. No position until a close.",
      attachments: [
        { type: "market", id: aid(), symbol: "BTCUSD" },
        {
          type: "signal",
          id: aid(),
          symbol: "BTCUSD",
          side: "BUY",
          timeframe: "H1",
          entry: 96600,
          target: 101200,
          stop: 95800,
          createdAt: daysAgo(0, 3),
        },
      ],
      hashtags: ["bitcoin", "btcusd", "setup"],
      createdAt: daysAgo(0, 3),
      engagement: 212,
      likes: 83,
      likedByMe: false,
      reposts: 21,
      repostedByMe: false,
      quotes: 6,
      bookmarks: 19,
      bookmarkedByMe: false,
      savedByMe: false,
      mutedByMe: false,
      blockedByMe: false,
    },
    {
      id: pid(),
      authorId: "u-macrotrader",
      text: "CPI recap: a firm core, but the market prefers to lean on the soft side. Expect the pair to stay range-bound into the press conference.",
      attachments: [],
      hashtags: ["macro", "fed", "cpi"],
      createdAt: daysAgo(1, 2),
      engagement: 340,
      likes: 140,
      likedByMe: false,
      reposts: 40,
      repostedByMe: false,
      quotes: 15,
      bookmarks: 22,
      bookmarkedByMe: false,
      savedByMe: false,
      mutedByMe: false,
      blockedByMe: false,
    },
    {
      id: pid(),
      authorId: "u-scalpqueen",
      text: "US500 scalping model for the afternoon session. Backtest note: the edge is in the first 90 minutes after the open — patience after that.",
      attachments: [
        { type: "chart", id: aid(), symbol: "US500", timeframe: "M15" },
      ],
      hashtags: ["us500", "scalping"],
      createdAt: daysAgo(1, 6),
      engagement: 144,
      likes: 52,
      likedByMe: false,
      reposts: 14,
      repostedByMe: false,
      quotes: 4,
      bookmarks: 25,
      bookmarkedByMe: false,
      savedByMe: false,
      mutedByMe: false,
      blockedByMe: false,
    },
    {
      id: pid(),
      authorId: "u-hedgehog",
      text: "Volatility crush into month-end. The VIX curve is pricing a quiet holiday week — sell premium with defined risk only.",
      attachments: [],
      hashtags: ["options", "vol", "vix"],
      createdAt: daysAgo(2, 4),
      engagement: 96,
      likes: 31,
      likedByMe: false,
      reposts: 9,
      repostedByMe: false,
      quotes: 2,
      bookmarks: 11,
      bookmarkedByMe: false,
      savedByMe: false,
      mutedByMe: false,
      blockedByMe: false,
    },
    {
      id: pid(),
      authorId: "u-goldfox",
      text: "Weekly gold review: higher lows on H4, momentum oscillator curling up. If 4,300 clears we extend into the 4,320 measured move.",
      attachments: [],
      hashtags: ["gold", "xauusd", "review"],
      createdAt: daysAgo(3, 5),
      engagement: 175,
      likes: 64,
      likedByMe: false,
      reposts: 18,
      repostedByMe: false,
      quotes: 7,
      bookmarks: 14,
      bookmarkedByMe: false,
      savedByMe: false,
      mutedByMe: false,
      blockedByMe: false,
    },
    {
      id: pid(),
      authorId: "u-btcstacker",
      text: "Funding reset on BTC. Perp funding back to neutral means the squeeze fuel is gone — range trading until the spot flow resumes.",
      attachments: [],
      hashtags: ["bitcoin", "funding", "flows"],
      createdAt: daysAgo(4, 2),
      engagement: 88,
      likes: 27,
      likedByMe: false,
      reposts: 8,
      repostedByMe: false,
      quotes: 1,
      bookmarks: 6,
      bookmarkedByMe: false,
      savedByMe: false,
      mutedByMe: false,
      blockedByMe: false,
    },
    {
      id: pid(),
      authorId: "u-macrotrader",
      text: "EURUSD — the rate differential keeps crowding the corners of the box. A snap back to the mid-band is the higher probability path.",
      attachments: [
        { type: "market", id: aid(), symbol: "EURUSD" },
      ],
      hashtags: ["fx", "eurusd", "macro"],
      createdAt: daysAgo(5, 6),
      engagement: 122,
      likes: 41,
      likedByMe: false,
      reposts: 13,
      repostedByMe: false,
      quotes: 5,
      bookmarks: 9,
      bookmarkedByMe: false,
      savedByMe: false,
      mutedByMe: false,
      blockedByMe: false,
    },
    {
      id: pid(),
      authorId: "u-scalpqueen",
      text: "Journal: today was about saying no to the 14:00 chop. Only 2 losses, both small. The rules beat the emotion — write yours down.",
      attachments: [],
      hashtags: ["journal", "discipline"],
      createdAt: daysAgo(6, 8),
      engagement: 210,
      likes: 96,
      likedByMe: false,
      reposts: 30,
      repostedByMe: false,
      quotes: 12,
      bookmarks: 33,
      bookmarkedByMe: false,
      savedByMe: false,
      mutedByMe: false,
      blockedByMe: false,
    },
    {
      id: pid(),
      authorId: "u-hedgehog",
      text: "New to the community? Introduce yourself — tell us what you trade, your timezone and one lesson the market taught you.",
      attachments: [],
      hashtags: ["community", "introduce"],
      createdAt: daysAgo(7, 1),
      engagement: 264,
      likes: 110,
      likedByMe: false,
      reposts: 22,
      repostedByMe: false,
      quotes: 19,
      bookmarks: 5,
      bookmarkedByMe: false,
      savedByMe: false,
      mutedByMe: false,
      blockedByMe: false,
    },
  ];
}

export function seedComments(): SocialComment[] {
  return [
    {
      id: cid(),
      postId: "p-1",
      parentId: null,
      authorId: "u-macrotrader",
      text: "Support zone aligns with the 50% retracement on D1 — agree with the bounce thesis.",
      createdAt: daysAgo(0, 0),
      likes: 12,
      likedByMe: false,
      reposts: 0,
      repostedByMe: false,
      reportedByMe: false,
      deletedByAuthor: false,
    },
    {
      id: cid(),
      postId: "p-1",
      parentId: null,
      authorId: "u-btcstacker",
      text: "Careful fading the squeeze — last three touches printed 30k+ moves first.",
      createdAt: daysAgo(0, 0),
      likes: 8,
      likedByMe: false,
      reposts: 1,
      repostedByMe: false,
      reportedByMe: false,
      deletedByAuthor: false,
    },
    {
      id: cid(),
      postId: "p-2",
      parentId: null,
      authorId: "u-goldfox",
      text: "Adding to favorites. The 101k target is deep but the structure supports it.",
      createdAt: daysAgo(0, 2),
      likes: 5,
      likedByMe: false,
      reposts: 0,
      repostedByMe: false,
      reportedByMe: false,
      deletedByAuthor: false,
    },
    {
      id: cid(),
      postId: "p-3",
      parentId: null,
      authorId: "u-hedgehog",
      text: "The dot-plot skew is the real driver here. Range trade unless the floor breaks.",
      createdAt: daysAgo(1, 0),
      likes: 7,
      likedByMe: false,
      reposts: 0,
      repostedByMe: false,
      reportedByMe: false,
      deletedByAuthor: false,
    },
  ];
}

export const SEED_NOTIFICATIONS: SocialNotification[] = [
  {
    id: "n-1",
    type: "follow",
    actorId: "u-goldfox",
    text: "GoldFox started following you",
    createdAt: daysAgo(0, 2),
    read: false,
  },
  {
    id: "n-2",
    type: "like",
    actorId: "u-btcstacker",
    postId: "p-1",
    text: "BTC Stacker liked your post",
    createdAt: daysAgo(1, 0),
    read: false,
  },
  {
    id: "n-3",
    type: "comment",
    actorId: "u-scalpqueen",
    postId: "p-1",
    text: "Scalp Queen replied to your post",
    createdAt: daysAgo(1, 4),
    read: true,
  },
];

export const SUGGESTED_TRADERS: SuggestedTrader[] = [
  { id: "u-goldfox", name: "GoldFox", handle: "goldfox", avatar: AVATARS[0], bio: "XAU trader" },
  { id: "u-macrotrader", name: "Macro Trader", handle: "macrotrader", avatar: AVATARS[1], bio: "Macro events" },
  { id: "u-btcstacker", name: "BTC Stacker", handle: "btcstacker", avatar: AVATARS[2], bio: "Bitcoin structure" },
  { id: "u-scalpqueen", name: "Scalp Queen", handle: "scalpqueen", avatar: AVATARS[3], bio: "M15 scalps" },
];

export const TRENDING_MARKETS: TrendingMarket[] = [
  { symbol: "XAUUSD", posts: 214, deltaPct: 0.42 },
  { symbol: "BTCUSD", posts: 189, deltaPct: -1.1 },
  { symbol: "EURUSD", posts: 96, deltaPct: 0.08 },
  { symbol: "US500", posts: 88, deltaPct: 0.31 },
];

export const TRENDING_TOPICS: TrendingTopic[] = [
  { title: "Gold breakout", posts: 214 },
  { title: "BTC resistance", posts: 189 },
  { title: "Market outlook", posts: 156 },
  { title: "Macro events", posts: 121 },
  { title: "Options vol", posts: 74 },
];

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

const STORAGE_KEY = "pkay.social.v1";

interface SocialState {
  users: SocialUser[];
  posts: SocialPost[];
  comments: SocialComment[];
  notifications: SocialNotification[];
  following: string[];
  muted: string[];
  me: SocialUser;
}

let state: SocialState | null = null;
const listeners = new Set<() => void>();

function read(): SocialState | null {
  return state;
}

function notify(): void {
  for (const listener of listeners) listener();
}

function defaultMe(): SocialUser {
  return {
    id: "me",
    name: "Guest Trader",
    handle: "guest",
    avatar: null,
    bio: "Learning the markets one journal at a time.",
    verified: false,
    followers: 12,
    following: 2,
    joinedAt: daysAgo(30),
  };
}

function load(): void {
  if (state) return;
  const base: SocialState = {
    users: SEED_USERS,
    posts: seedPosts(),
    comments: seedComments(),
    notifications: SEED_NOTIFICATIONS,
    following: ["u-goldfox", "u-btcstacker"],
    muted: [],
    me: defaultMe(),
  };
  // Safe on the server too: the Navbar's notification bell consumes this hook,
  // so it must render without a browser. localStorage is only read client-side.
  state = base;
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<SocialState>;
      state = {
        ...base,
        ...parsed,
        users: parsed.users?.length ? parsed.users : base.users,
        posts: parsed.posts?.length ? parsed.posts : base.posts,
        comments: parsed.comments ?? base.comments,
        notifications: parsed.notifications ?? base.notifications,
        following: parsed.following ?? base.following,
      };
    }
  } catch {
    /* fall through to seed */
  }
}

function persist(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    /* storage unavailable */
  }
}

function commit(mutate: (draft: SocialState) => void): void {
  load();
  if (!state) return;
  mutate(state);
  persist();
  notify();
}

function uid(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}${Date.now().toString(36).slice(-4)}`;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useSocial(): {
  users: SocialUser[];
  posts: SocialPost[];
  comments: SocialComment[];
  notifications: SocialNotification[];
  following: string[];
  muted: string[];
  me: SocialUser;
  userById: (id: string) => SocialUser | undefined;
  isFollowing: (userId: string) => boolean;
  postsByUser: (userId: string) => SocialPost[];
  commentsForPost: (postId: string) => SocialComment[];
  addPost: (input: {
    text: string;
    attachments: PostAttachment[];
    hashtags: string[];
    authorId?: string;
  }) => void;
  toggleLike: (postId: string) => void;
  toggleRepost: (postId: string) => void;
  toggleBookmark: (postId: string) => void;
  toggleSave: (postId: string) => void;
  toggleMutePost: (postId: string) => void;
  blockPost: (postId: string) => void;
  addComment: (postId: string, parentId: string | null, text: string) => void;
  toggleCommentLike: (commentId: string, postId: string) => void;
  toggleCommentRepost: (commentId: string, postId: string) => void;
  deleteComment: (commentId: string, postId: string) => void;
  reportComment: (commentId: string, postId: string) => void;
  followUser: (userId: string) => void;
  unfollowUser: (userId: string) => void;
  markAllNotificationsRead: () => void;
  unreadCount: number;
  setMe: (me: SocialUser) => void;
} {
  load();
  const snapshot = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    read,
    read,
  );

  const s = snapshot ?? (state as SocialState);
  const userById = useCallback((id: string) => s.users.find((u) => u.id === id), [s.users]);

  return {
    users: s.users,
    posts: s.posts,
    comments: s.comments,
    notifications: s.notifications,
    following: s.following,
    muted: s.muted,
    me: s.me,
    userById,
    isFollowing: useCallback(
      (userId: string) => s.following.includes(userId),
      [s.following],
    ),
    postsByUser: useCallback(
      (userId: string) => s.posts.filter((p) => p.authorId === userId),
      [s.posts],
    ),
    commentsForPost: useCallback(
      (postId: string) => s.comments.filter((c) => c.postId === postId),
      [s.comments],
    ),
    addPost: useCallback(
      (input) => {
        commit((draft) => {
          draft.posts = [
            {
              id: pid(),
              authorId: input.authorId ?? draft.me.id,
              text: input.text,
              attachments: input.attachments,
              hashtags: input.hashtags,
              createdAt: new Date().toISOString(),
              engagement: 1,
              likes: 0,
              likedByMe: false,
              reposts: 0,
              repostedByMe: false,
              quotes: 0,
              bookmarks: 0,
              bookmarkedByMe: false,
              savedByMe: false,
              mutedByMe: false,
              blockedByMe: false,
            },
            ...draft.posts,
          ];
        });
      },
      [],
    ),
    toggleLike: useCallback((postId) => {
      commit((draft) => {
        draft.posts = draft.posts.map((post) => {
          if (post.id !== postId) return post;
          const likedByMe = !post.likedByMe;
          return {
            ...post,
            likedByMe,
            likes: post.likes + (likedByMe ? 1 : -1),
            engagement: post.engagement + (likedByMe ? 2 : -2),
          };
        });
      });
    }, []),
    toggleRepost: useCallback((postId) => {
      commit((draft) => {
        draft.posts = draft.posts.map((post) => {
          if (post.id !== postId) return post;
          const repostedByMe = !post.repostedByMe;
          return {
            ...post,
            repostedByMe,
            reposts: post.reposts + (repostedByMe ? 1 : -1),
          };
        });
      });
    }, []),
    toggleBookmark: useCallback((postId) => {
      commit((draft) => {
        draft.posts = draft.posts.map((post) => {
          if (post.id !== postId) return post;
          const bookmarkedByMe = !post.bookmarkedByMe;
          return {
            ...post,
            bookmarkedByMe,
            bookmarks: post.bookmarks + (bookmarkedByMe ? 1 : -1),
          };
        });
      });
    }, []),
    toggleSave: useCallback((postId) => {
      commit((draft) => {
        draft.posts = draft.posts.map((post) =>
          post.id === postId ? { ...post, savedByMe: !post.savedByMe } : post,
        );
      });
    }, []),
    toggleMutePost: useCallback((postId) => {
      commit((draft) => {
        draft.posts = draft.posts.map((post) =>
          post.id === postId ? { ...post, mutedByMe: !post.mutedByMe } : post,
        );
      });
    }, []),
    blockPost: useCallback((postId) => {
      commit((draft) => {
        draft.posts = draft.posts.map((post) =>
          post.id === postId ? { ...post, blockedByMe: true } : post,
        );
      });
    }, []),
    addComment: useCallback((postId, parentId, text) => {
      const authorId = state?.me.id ?? "me";
      const author = state?.users.find((u) => u.id === authorId) ?? state?.me;
      const name = author?.name ?? "Guest";
      commit((draft) => {
        draft.comments = [
          {
            id: cid(),
            postId,
            parentId,
            authorId: draft.me.id,
            text,
            createdAt: new Date().toISOString(),
            likes: 0,
            likedByMe: false,
            reposts: 0,
            repostedByMe: false,
            reportedByMe: false,
            deletedByAuthor: false,
          },
          ...draft.comments,
        ];
        if (parentId) {
          draft.notifications.unshift({
            id: uid("n"),
            type: "reply",
            actorId: draft.me.id,
            postId,
            text: `${name} replied to a comment`,
            createdAt: new Date().toISOString(),
            read: false,
          });
        } else {
          draft.notifications.unshift({
            id: uid("n"),
            type: "comment",
            actorId: draft.me.id,
            postId,
            text: `${name} commented on a post`,
            createdAt: new Date().toISOString(),
            read: false,
          });
        }
      });
    }, []),
    toggleCommentLike: useCallback((commentId, postId) => {
      commit((draft) => {
        draft.comments = draft.comments.map((comment) => {
          if (comment.id !== commentId || comment.postId !== postId) return comment;
          const likedByMe = !comment.likedByMe;
          return { ...comment, likedByMe, likes: comment.likes + (likedByMe ? 1 : -1) };
        });
      });
    }, []),
    toggleCommentRepost: useCallback((commentId, postId) => {
      commit((draft) => {
        draft.comments = draft.comments.map((comment) => {
          if (comment.id !== commentId || comment.postId !== postId) return comment;
          const repostedByMe = !comment.repostedByMe;
          return { ...comment, repostedByMe, reposts: comment.reposts + (repostedByMe ? 1 : -1) };
        });
      });
    }, []),
    deleteComment: useCallback((commentId, postId) => {
      commit((draft) => {
        draft.comments = draft.comments.map((comment) =>
          comment.id === commentId && comment.postId === postId
            ? { ...comment, deletedByAuthor: true }
            : comment,
        );
      });
    }, []),
    reportComment: useCallback((commentId, postId) => {
      commit((draft) => {
        draft.comments = draft.comments.map((comment) =>
          comment.id === commentId && comment.postId === postId
            ? { ...comment, reportedByMe: true }
            : comment,
        );
      });
    }, []),
    followUser: useCallback((userId) => {
      commit((draft) => {
        if (draft.following.includes(userId)) return;
        draft.following = [...draft.following, userId];
        draft.users = draft.users.map((u) =>
          u.id === userId ? { ...u, followers: u.followers + 1 } : u,
        );
        const target = draft.users.find((u) => u.id === userId);
        draft.notifications.unshift({
          id: uid("n"),
          type: "follow",
          actorId: draft.me.id,
          text: `You followed ${target?.name ?? "a trader"}`,
          createdAt: new Date().toISOString(),
          read: false,
        });
      });
    }, []),
    unfollowUser: useCallback((userId) => {
      commit((draft) => {
        draft.following = draft.following.filter((id) => id !== userId);
        draft.users = draft.users.map((u) =>
          u.id === userId ? { ...u, followers: Math.max(0, u.followers - 1) } : u,
        );
      });
    }, []),
    markAllNotificationsRead: useCallback(() => {
      commit((draft) => {
        draft.notifications = draft.notifications.map((n) => ({ ...n, read: true }));
      });
    }, []),
    unreadCount: s.notifications.filter((n) => !n.read).length,
    setMe: useCallback((me: SocialUser) => {
      commit((draft) => {
        draft.me = me;
      });
    }, []),
  };
}

/** Derive the recommended feed for a tab, newest first with stable ordering. */
export function feedForTab(
  posts: SocialPost[],
  tab: FeedTab,
  following: string[],
  page: number,
  pageSize = 6,
): SocialPost[] {
  let filtered = [...posts].filter((p) => !p.blockedByMe && !p.mutedByMe);
  if (tab === "following") {
    filtered = filtered.filter((p) => following.includes(p.authorId));
  } else if (tab === "trending") {
    filtered = filtered
      .filter((p) => p.engagement > 40)
      .sort((a, b) => b.engagement - a.engagement);
  } else {
    filtered = filtered.sort(
      (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
    );
  }
  return filtered.slice(0, page * pageSize);
}