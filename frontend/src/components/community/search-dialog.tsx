"use client";

import { useMemo, useState } from "react";
import { HashIcon, SearchIcon, TrendingUpIcon, UsersIcon } from "lucide-react";

import { UserAvatar } from "@/components/community/shared";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import type { SocialPost, SocialUser } from "@/hooks/use-social";

export interface SearchResults {
  users: SocialUser[];
  posts: SocialPost[];
  markets: string[];
  hashtags: string[];
  topics: string[];
}

/**
 * Community search dialog: users, posts, markets, hashtags and topics resolve
 * live as you type without leaving the Community experience.
 */
export function SearchDialog({
  open,
  onOpenChange,
  users,
  posts,
  markets,
  topics,
  onOpenUser,
  onOpenPost,
  onOpenMarket,
  onFilterTopic,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  users: SocialUser[];
  posts: SocialPost[];
  markets: string[];
  topics: string[];
  onOpenUser: (userId: string) => void;
  onOpenPost: (postId: string) => void;
  onOpenMarket: (symbol: string) => void;
  onFilterTopic: (topic: string) => void;
}) {
  const [query, setQuery] = useState("");

  const results = useMemo<SearchResults>(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return { users: [], posts: [], markets: [], hashtags: [], topics: [] };

    const allHashtags = Array.from(
      new Set(posts.flatMap((post) => post.hashtags.map((tag) => tag.toLowerCase()))),
    );
    const allMarkets = Array.from(new Set([...markets, ...posts.flatMap((post) =>
      post.attachments
        .map((attachment) => (attachment.type === "market" || attachment.type === "chart" ? attachment.symbol : null))
        .filter((symbol): symbol is string => Boolean(symbol)),
    )]));

    return {
      users: users.filter(
        (user) =>
          user.name.toLowerCase().includes(needle) || user.handle.toLowerCase().includes(needle),
      ),
      posts: posts.filter(
        (post) =>
          post.text.toLowerCase().includes(needle) ||
          post.hashtags.some((tag) => `#${tag}`.toLowerCase().includes(needle)),
      ),
      markets: allMarkets.filter((symbol) => symbol.toLowerCase().includes(needle)),
      hashtags: allHashtags.filter((tag) => `#${tag}`.includes(needle)),
      topics: topics.filter((topic) => topic.toLowerCase().includes(needle)),
    };
  }, [query, users, posts, markets, topics]);

  const total =
    results.users.length +
    results.posts.length +
    results.markets.length +
    results.hashtags.length +
    results.topics.length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg bg-card sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base">
            <SearchIcon className="size-4" /> Search community
          </DialogTitle>
        </DialogHeader>

        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search traders, posts, markets, hashtags…"
          autoFocus
        />

        {query.trim() === "" ? (
          <p className="py-8 text-center text-xs text-muted-foreground">
            Search users, posts, markets, hashtags and topics.
          </p>
        ) : total === 0 ? (
          <p className="py-8 text-center text-xs text-muted-foreground">
            No results for “{query}”.
          </p>
        ) : (
          <div className="max-h-80 space-y-4 overflow-y-auto">
            {results.users.length > 0 ? (
              <Group label={`Traders (${results.users.length})`} icon={<UsersIcon className="size-3.5" />}>
                {results.users.map((user) => (
                  <button
                    key={user.id}
                    type="button"
                    onClick={() => {
                      onOpenUser(user.id);
                      setQuery("");
                      onOpenChange(false);
                    }}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-accent/40"
                  >
                    <UserAvatar user={user} size="sm" />
                    <div className="min-w-0">
                      <div className="truncate text-xs font-medium">{user.name}</div>
                      <div className="text-[11px] text-muted-foreground">@{user.handle}</div>
                    </div>
                  </button>
                ))}
              </Group>
            ) : null}

            {results.hashtags.length > 0 ? (
              <Group label={`Hashtags (${results.hashtags.length})`} icon={<HashIcon className="size-3.5" />}>
                {results.hashtags.map((tag) => (
                  <button
                    key={tag}
                    type="button"
                    onClick={() => onOpenChange(false)}
                    className="block w-full rounded-lg px-2 py-1.5 text-left text-xs text-blue-500 transition-colors hover:bg-accent/40"
                  >
                    #{tag}
                  </button>
                ))}
              </Group>
            ) : null}

            {results.markets.length > 0 ? (
              <Group label={`Markets (${results.markets.length})`} icon={<TrendingUpIcon className="size-3.5" />}>
                {results.markets.map((symbol) => (
                  <button
                    key={symbol}
                    type="button"
                    onClick={() => {
                      onOpenMarket(symbol);
                      setQuery("");
                      onOpenChange(false);
                    }}
                    className="block w-full rounded-lg px-2 py-1.5 text-left text-xs font-medium uppercase transition-colors hover:bg-accent/40"
                  >
                    {symbol}
                  </button>
                ))}
              </Group>
            ) : null}

            {results.topics.length > 0 ? (
              <Group label={`Topics (${results.topics.length})`} icon={<HashIcon className="size-3.5" />}>
                {results.topics.map((topic) => (
                  <button
                    key={topic}
                    type="button"
                    onClick={() => {
                      onFilterTopic(topic);
                      setQuery("");
                      onOpenChange(false);
                    }}
                    className="block w-full rounded-lg px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent/40"
                  >
                    {topic}
                  </button>
                ))}
              </Group>
            ) : null}

            {results.posts.length > 0 ? (
              <Group label={`Posts (${results.posts.length})`} icon={<SearchIcon className="size-3.5" />}>
                {results.posts.slice(0, 6).map((post) => (
                  <button
                    key={post.id}
                    type="button"
                    onClick={() => {
                      onOpenPost(post.id);
                      setQuery("");
                      onOpenChange(false);
                    }}
                    className="block w-full rounded-lg border border-border/60 px-2.5 py-2 text-left transition-colors hover:bg-accent/40"
                  >
                    <p className="line-clamp-1 text-xs text-foreground/85">{post.text}</p>
                    <span className="text-[10px] text-muted-foreground">
                      {post.hashtags.map((tag) => `#${tag}`).join(" ")}
                    </span>
                  </button>
                ))}
              </Group>
            ) : null}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Group({
  label,
  icon,
  children,
}: {
  label: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
        {icon}
        {label}
      </div>
      {children}
    </div>
  );
}