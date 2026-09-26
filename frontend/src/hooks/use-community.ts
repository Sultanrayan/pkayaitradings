"use client";

import { useCallback, useSyncExternalStore } from "react";

export interface CommunityAuthor {
  name: string;
  handle: string;
  avatar: string | null;
}

export interface CommunityComment {
  id: string;
  author: CommunityAuthor;
  text: string;
  createdAt: string;
}

export interface CommunityPost {
  id: string;
  author: CommunityAuthor;
  title: string;
  caption: string;
  hashtags: string[];
  image: string | null;
  createdAt: string;
  likes: number;
  likedByMe: boolean;
  comments: CommunityComment[];
}

export interface NewPostInput {
  author: CommunityAuthor;
  title: string;
  caption: string;
  hashtags: string[];
  image: string | null;
}

const STORAGE_KEY = "pkay.community.posts";

let current: CommunityPost[] = [];
let hydrated = false;
const listeners = new Set<() => void>();

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function read(): CommunityPost[] {
  return current;
}

function notify(): void {
  for (const listener of listeners) listener();
}

function persist(): void {
  notify();
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
  } catch {
    /* storage unavailable */
  }
}

function isPost(value: unknown): value is CommunityPost {
  if (typeof value !== "object" || value === null) return false;
  const post = value as Record<string, unknown>;
  return (
    typeof post.id === "string" &&
    typeof post.caption === "string" &&
    Array.isArray(post.comments) &&
    typeof post.likes === "number"
  );
}

function seed(): CommunityPost[] {
  const now = Date.now();
  const minute = 60_000;
  return [
    {
      id: uid(),
      author: { name: "Pkay Signal Desk", handle: "signaldesk", avatar: "/agents/technical_analyst.jpg" },
      title: "XAUUSD breakout watch",
      caption:
        "Gold is holding support after the macro release. Watching a breakout above the session high — the momentum and trend filters are still aligned long. Managing risk with stops below the swing low.",
      hashtags: ["gold", "xauusd", "setup", "goldbugs"],
      image: "/agents/technical_analyst.jpg",
      createdAt: new Date(now - 42 * minute).toISOString(),
      likes: 24,
      likedByMe: false,
      comments: [
        {
          id: uid(),
          author: { name: "Risk Desk", handle: "riskdesk", avatar: "/agents/risk_manager.jpg" },
          text: "Stops below the swing low look reasonable here, VaR stays inside budget.",
          createdAt: new Date(now - 30 * minute).toISOString(),
        },
        {
          id: uid(),
          author: { name: "Macro Monitor", handle: "macro", avatar: "/agents/news_monitor.jpg" },
          text: "The calendar is quiet for the next session, so clean technicals should lead.",
          createdAt: new Date(now - 18 * minute).toISOString(),
        },
      ],
    },
    {
      id: uid(),
      author: { name: "Top Step Trader", handle: "topstep", avatar: "/agents/decision_maker.jpg" },
      title: "My BTCUSD plan for today",
      caption:
        "Range structure on BTC with the shorter timeframes offering a long entry close to the value zone. First target the session high, second target the weekly pivot. No news catalyst today so rely on levels.",
      hashtags: ["bitcoin", "btcusd", "intraday", "riskfirst"],
      image: "/logo-pkay.jpg",
      createdAt: new Date(now - 3 * 60 * minute).toISOString(),
      likes: 41,
      likedByMe: false,
      comments: [
        {
          id: uid(),
          author: { name: "Top Step Trader", handle: "topstep", avatar: "/agents/decision_maker.jpg" },
          text: "Adding the exact levels in a follow-up post if anyone is interested.",
          createdAt: new Date(now - 2 * 60 * minute).toISOString(),
        },
      ],
    },
  ];
}

function hydrate(): void {
  if (hydrated || typeof window === "undefined") return;
  hydrated = true;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed)) {
        current = parsed.filter(isPost);
      }
    }
  } catch {
    current = [];
  }
  if (current.length === 0) {
    current = seed();
    persist();
  }
}

function addPost(input: NewPostInput): void {
  hydrate();
  const post: CommunityPost = {
    id: uid(),
    author: input.author,
    title: input.title.trim(),
    caption: input.caption.trim(),
    hashtags: input.hashtags,
    image: input.image,
    createdAt: new Date().toISOString(),
    likes: 0,
    likedByMe: false,
    comments: [],
  };
  current = [post, ...current];
  persist();
}

function toggleLike(postId: string): void {
  hydrate();
  current = current.map((post) =>
    post.id === postId
      ? {
          ...post,
          likedByMe: !post.likedByMe,
          likes: post.likes + (post.likedByMe ? -1 : 1),
        }
      : post,
  );
  persist();
}

function addComment(postId: string, author: CommunityAuthor, text: string): void {
  hydrate();
  current = current.map((post) =>
    post.id === postId
      ? {
          ...post,
          comments: [
            ...post.comments,
            { id: uid(), author, text: text.trim(), createdAt: new Date().toISOString() },
          ],
        }
      : post,
  );
  persist();
}

/**
 * Community posts + comments backed by localStorage, exposed through
 * `useSyncExternalStore` so all open panels stay in sync.
 */
export function useCommunity(): {
  posts: CommunityPost[];
  addPost: (input: NewPostInput) => void;
  toggleLike: (postId: string) => void;
  addComment: (postId: string, author: CommunityAuthor, text: string) => void;
} {
  hydrate();
  const posts = useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    read,
    read,
  );
  return {
    posts,
    addPost: useCallback((input: NewPostInput) => addPost(input), []),
    toggleLike: useCallback((postId: string) => toggleLike(postId), []),
    addComment: useCallback(
      (postId: string, author: CommunityAuthor, text: string) =>
        addComment(postId, author, text),
      [],
    ),
  };
}

/** Shared helpers for parsing hashtag input. */
export function parseHashtags(raw: string): string[] {
  const seen = new Set<string>();
  const tags = raw.split(/[\s,]+/);
  for (const part of tags) {
    const cleaned = part.replace(/^#+/, "").trim();
    if (cleaned) seen.add(cleaned);
  }
  return [...seen];
}