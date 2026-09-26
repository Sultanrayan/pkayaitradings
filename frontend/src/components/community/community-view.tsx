"use client";

import { useMemo, useState } from "react";
import { NewspaperIcon, UsersIcon } from "lucide-react";
import { cn } from "cn";

import { CreatePostDialog } from "@/components/community/create-post-dialog";
import { CommunityPostCard } from "@/components/community/post-card";
import { PageHeader } from "@/components/shared/primitives";
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
} from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/components/auth-provider";
import { useCommunity, type CommunityAuthor } from "@/hooks/use-community";
import { useNews } from "@/hooks/use-api";
import { useDemoMode } from "@/hooks/use-demo-market";
import { useMarketContext } from "@/components/symbol-provider";
import { demoAsset } from "@/lib/demo-data";
import { formatDateTime } from "@/lib/format";

/** Demo headlines when no backend is running. */
function demoNews(symbol: string) {
  const asset = demoAsset(symbol);
  const base = asset.base;
  return [
    {
      url: "#",
      title: `${symbol} holds range after macro data`,
      description: `Price is consolidating near ${base.toLocaleString()} as traders weigh the latest release.`,
      publisher: "Market Wire",
      publishedDate: new Date(Date.now() - 8 * 60_000).toISOString(),
    },
    {
      url: "#",
      title: "Central bank commentary keeps gold traders on edge",
      description: "Speakers were mixed; implied volatility picked up around the session open.",
      publisher: "Commodity Update",
      publishedDate: new Date(Date.now() - 42 * 60_000).toISOString(),
    },
    {
      url: "#",
      title: "Weekend positioning points to a quiet close",
      description: "Flows thin into the weekend — levels are the guide for the community.",
      publisher: "Desk Notes",
      publishedDate: new Date(Date.now() - 70 * 60_000).toISOString(),
    },
    {
      url: "#",
      title: "Technical round-up: bias stays constructive",
      description: "The trend filters remain aligned while the shorter timeframes cool off.",
      publisher: "Signal Feed",
      publishedDate: new Date(Date.now() - 2 * 60 * 60_000).toISOString(),
    },
  ];
}

export function CommunityView() {
  const { symbol } = useMarketContext();
  const { user } = useAuth();
  const demo = useDemoMode();
  const { posts, addPost, toggleLike, addComment } = useCommunity();
  const news = useNews(symbol, 6);
  const [composerOpen, setComposerOpen] = useState(false);

  const currentUser = useMemo<CommunityAuthor | null>(
    () =>
      user
        ? {
            name: user.name,
            handle: user.email.split("@")[0] ?? user.name.toLowerCase().replace(/\s+/g, ""),
            avatar: null,
          }
        : null,
    [user],
  );

  const headlines = demo || news.error ? demoNews(symbol) : news.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <UsersIcon className="size-5" /> Community
          </span>
        }
        description="Facebook-style feed — post ideas, comment on threads and follow the news."
      />

      {/* Left column (larger): posts · Right column (smaller): news */}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        {/* Posts */}
        <section className="min-w-0 space-y-4">
          {/* Create post action */}
          <Card className="flex items-center justify-between gap-3 p-3 ring-border">
            <div className="flex min-w-0 items-center gap-3">
              {currentUser ? (
                <Avatar>
                  {currentUser.avatar ? <AvatarImage src={currentUser.avatar} alt="" /> : null}
                  <AvatarFallback>
                    {currentUser.name.slice(0, 1).toUpperCase()}
                  </AvatarFallback>
                </Avatar>
              ) : (
                <Avatar>
                  <AvatarFallback>G</AvatarFallback>
                </Avatar>
              )}
              <span className="truncate text-sm text-muted-foreground">
                {currentUser ? `What's on your mind, ${currentUser.name.split(" ")[0]}?` : "What's on your mind?"}
              </span>
            </div>
            <Button onClick={() => setComposerOpen(true)} className="shrink-0">
              Create post
            </Button>
          </Card>

          {posts.length === 0 ? (
            <Card className="p-8 text-center text-sm text-muted-foreground ring-border">
              No posts yet — be the first to share an idea.
            </Card>
          ) : (
            posts.map((post) => (
              <CommunityPostCard
                key={post.id}
                post={post}
                currentUser={currentUser}
                onToggleLike={toggleLike}
                onAddComment={addComment}
              />
            ))
          )}
        </section>

        {/* News */}
        <aside className="min-w-0">
          <Card className="ring-border">
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <NewspaperIcon className="size-4" /> News
                <span className="ml-auto text-[11px] font-normal text-muted-foreground">
                  {symbol}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="px-2 pb-2">
              {!demo && news.loading && news.data.length === 0 ? (
                <div className="space-y-2 px-2">
                  {Array.from({ length: 4 }).map((_, index) => (
                    <Skeleton key={index} className="h-16 w-full bg-muted" />
                  ))}
                </div>
              ) : (
                <div className="divide-y divide-border/70">
                  {headlines.map((article) => (
                    <a
                      key={article.url + article.title}
                      href={article.url === "#" ? undefined : article.url}
                      target={article.url === "#" ? undefined : "_blank"}
                      rel="noopener noreferrer"
                      className={cn(
                        "block px-2 py-2.5 transition-colors",
                        article.url !== "#" && "hover:bg-accent/40",
                      )}
                    >
                      <div className="text-[13px] leading-snug font-medium">{article.title}</div>
                      {article.description ? (
                        <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                          {article.description}
                        </p>
                      ) : null}
                      <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                        <span className="truncate">{article.publisher}</span>
                        <span className="tabular">{formatDateTime(article.publishedDate)}</span>
                      </div>
                    </a>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </aside>
      </div>

      <CreatePostDialog
        open={composerOpen}
        onOpenChange={setComposerOpen}
        onSubmit={(payload) => {
          if (!currentUser) {
            addPost({
              author: { name: "Guest Trader", handle: "guest", avatar: null },
              ...payload,
            });
          } else {
            addPost({ author: currentUser, ...payload });
          }
        }}
      />
    </div>
  );
}