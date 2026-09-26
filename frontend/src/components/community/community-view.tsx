"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth-provider";
import { CommunityHeader } from "@/components/community/community-header";
import { PostComposer } from "@/components/community/post-composer";
import { FeedTabs } from "@/components/community/feed-tabs";
import { PostCard } from "@/components/community/post-card";
import { SearchDialog } from "@/components/community/search-dialog";
import {
  SidebarSkeletons,
  PostSkeletons,
  EmptyFeed,
  FeedError,
} from "@/components/community/states";
import {
  SuggestedTraders,
  TrendingDiscussions,
  TrendingMarkets,
} from "@/components/community/sidebar";
import { UserProfileDialog } from "@/components/community/user-profile";
import { setCommunityBotContext } from "@/lib/community-bot-context";
import { useMarketContext } from "@/components/symbol-provider";
import { useSocial, feedForTab, hydrateCommunityFromServer, SUGGESTED_TRADERS, TRENDING_MARKETS, TRENDING_TOPICS } from "@/hooks/use-social";
import type { FeedTab } from "@/hooks/use-social";

const PAGE_SIZE = 6;

export function CommunityView() {
  const router = useRouter();
  const { user: authUser } = useAuth();
  const social = useSocial();
  const { symbols, setSymbol } = useMarketContext();

  const [tab, setTab] = useState<FeedTab>("forYou");
  const [page, setPage] = useState(1);
  const [searchOpen, setSearchOpen] = useState(false);
  const [profileUser, setProfileUser] = useState<string | null>(null);
  const [error, setError] = useState<boolean>(false);
  const [bootstrapping, setBootstrapping] = useState(true);
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  // The current user "me" — synced from the auth session where available.
  const me = useMemo<Social["me"]>(() => {
    if (authUser) {
      return {
        ...social.me,
        name: authUser.name,
        handle: authUser.email.split("@")[0] ?? authUser.name.toLowerCase().replace(/\s+/g, ""),
        avatar: null,
      };
    }
    return social.me;
  }, [authUser, social.me]);

  // Hydrate from the real backend once, keeping the local seed as fallback.
  useEffect(() => {
    void hydrateCommunityFromServer();
  }, []);

  // Simulated load: skeleton first, then feed (and simulate an error condition
  // once so the error state can be verified without breaking the page).
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setError((previous) => previous || Math.random() < 0.02);
      setBootstrapping(false);
    }, 600);
    return () => window.clearTimeout(timer);
  }, []);

  const visiblePosts = useMemo(
    () => feedForTab(social.posts, tab, social.following, page, PAGE_SIZE),
    [social.posts, tab, social.following, page],
  );
  const hasMore = visiblePosts.length < social.posts.length;
  const followingCount = social.posts.filter((p) => social.following.includes(p.authorId)).length;

  // Infinite scroll: extend the page when the sentinel becomes visible.
  useEffect(() => {
    const node = sentinelRef.current;
    if (!node || error || bootstrapping) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && hasMore) {
          setPage((value) => value + 1);
        }
      },
      { rootMargin: "240px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [hasMore, error, bootstrapping, page]);

  const openMarket = useCallback(
    (symbol: string) => {
      setSymbol(symbol);
      router.push("/dashboard");
    },
    [setSymbol, router],
  );

  const openProfile = useCallback((userId: string) => setProfileUser(userId), []);
  const onOpenPostFromProfile = useCallback(() => {
    setProfileUser(null);
    setTab("forYou");
  }, []);

  const analyzeWithAI = useCallback(
    (postId: string) => {
      const post = social.posts.find((p) => p.id === postId);
      const author = post ? social.userById(post.authorId) : undefined;
      if (!post) return;
      const symbol = post.attachments.find(
        (attachment) => attachment.type === "market" || attachment.type === "chart",
      );
      setCommunityBotContext({
        label: `post by ${author?.name ?? "trader"}`,
        detail: post.text,
        symbol: symbol ? symbol.symbol : undefined,
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [social.posts, social.userById],
  );

  const bookmark = useCallback(
    (postId: string) => social.toggleBookmark(postId),
    [social],
  );

  const copyLink = useCallback((postId: string) => {
    void navigator.clipboard?.writeText(`${window.location.origin}/community#post-${postId}`);
  }, []);

  const quote = useCallback(
    (postId: string) => {
      const post = social.posts.find((p) => p.id === postId);
      if (!post) return;
      setTab("forYou");
      // Quote composer is part of the PostComposer; prefill via a custom event.
      window.dispatchEvent(new CustomEvent("pkay:quote", { detail: { text: post.text } }));
    },
    [social.posts],
  );

  const share = useCallback((postId: string) => {
    void navigator.clipboard?.writeText(`${window.location.origin}/community#post-${postId}`);
  }, []);

  const topicFilter = useCallback(() => {
    setTab("forYou");
    setSearchOpen(false);
  }, []);

  const commentsFor = (postId: string) => social.comments.filter((c) => c.postId === postId);

  const selectedUser = profileUser ? social.userById(profileUser) ?? null : null;

  return (
    <div className="space-y-6">
      <CommunityHeader onSearch={() => setSearchOpen(true)} />

      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.7fr)_minmax(300px,1fr)]">
        {/* Main feed */}
        <section className="min-w-0 space-y-4">
          <PostComposer
            me={me}
            symbols={symbols.length ? symbols : ["XAUUSD", "BTCUSD", "EURUSD", "US500"]}
            onPost={({ text, attachments, hashtags }) => {
              social.addPost({ text, attachments, hashtags });
              setTab("forYou");
            }}
          />

          <FeedTabs
            active={tab}
            onChange={(next) => {
              setTab(next);
              setPage(1);
            }}
            counts={{
              forYou: social.posts.length,
              following: followingCount,
              trending: social.posts.filter((p) => p.engagement > 40).length,
            }}
          />

          {error ? (
            <FeedError onRetry={() => setError(false)} />
          ) : bootstrapping ? (
            <PostSkeletons count={4} />
          ) : visiblePosts.length === 0 ? (
            <EmptyFeed
              title={
                tab === "following"
                  ? "No posts from people you follow yet."
                  : tab === "trending"
                    ? "No trending discussions right now."
                    : "No posts yet."
              }
              hint={tab === "following" ? "Follow traders to build your feed." : undefined}
              actionLabel={tab === "following" ? "Discover traders" : undefined}
              onAction={
                tab === "following"
                  ? () => setTab("trending")
                  : undefined
              }
            />
          ) : (
            <>
              <div className="space-y-4">
                {visiblePosts.map((post) => (
                  <PostCard
                    key={post.id}
                    post={post}
                    author={social.userById(post.authorId)}
                    me={me}
                    isFollowing={social.following.includes(post.authorId)}
                    comments={commentsFor(post.id)}
                    onToggleFollow={(userId) =>
                      social.following.includes(userId)
                        ? social.unfollowUser(userId)
                        : social.followUser(userId)
                    }
                    onLike={social.toggleLike}
                    onRepost={social.toggleRepost}
                    onBookmark={bookmark}
                    onShare={share}
                    onQuote={quote}
                    onSave={(id) => social.toggleSave(id)}
                    onCopyLink={copyLink}
                    onReport={() => undefined}
                    onMute={(id) => social.toggleMutePost(id)}
                    onBlock={(id) => social.blockPost(id)}
                    onAnalyze={analyzeWithAI}
                    onOpenMarket={openMarket}
                    onOpenProfile={openProfile}
                    onAddComment={(postId, text) => social.addComment(postId, null, text)}
                    onReplyToComment={(postId, commentId, text) =>
                      social.addComment(postId, commentId, text)
                    }
                    onToggleCommentLike={(commentId, postId) =>
                      social.toggleCommentLike(commentId, postId)
                    }
                    onToggleCommentRepost={(commentId, postId) =>
                      social.toggleCommentRepost(commentId, postId)
                    }
                    onDeleteComment={(commentId, postId) =>
                      social.deleteComment(commentId, postId)
                    }
                    onReportComment={(commentId, postId) =>
                      social.reportComment(commentId, postId)
                    }
                    usersById={social.userById}
                  />
                ))}
              </div>

              {/* Infinite load sentinel */}
              <div ref={sentinelRef} className="flex justify-center py-4">
                {hasMore ? (
                  <span className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="size-3 animate-spin rounded-full border-2 border-border border-t-foreground" />
                    Loading more…
                  </span>
                ) : (
                  <span className="text-xs text-muted-foreground">
                    You&apos;re all caught up — nothing more to load.
                  </span>
                )}
              </div>
            </>
          )}
        </section>

        {/* Right sidebar */}
        <aside className="min-w-0 space-y-4 lg:sticky lg:top-20">
          {bootstrapping ? (
            <SidebarSkeletons />
          ) : (
            <>
              <TrendingMarkets markets={TRENDING_MARKETS} onOpenMarket={openMarket} />
              <TrendingDiscussions topics={TRENDING_TOPICS} onSelectTopic={topicFilter} />
              <SuggestedTraders
                traders={SUGGESTED_TRADERS}
                following={social.following}
                onFollowToggle={(userId) =>
                  social.following.includes(userId)
                    ? social.unfollowUser(userId)
                    : social.followUser(userId)
                }
                onOpenProfile={openProfile}
              />
            </>
          )}
        </aside>
      </div>

      <SearchDialog
        open={searchOpen}
        onOpenChange={setSearchOpen}
        users={social.users}
        posts={social.posts}
        markets={symbols}
        topics={TRENDING_TOPICS.map((topic) => topic.title)}
        onOpenUser={openProfile}
        onOpenPost={onOpenPostFromProfile}
        onOpenMarket={openMarket}
        onFilterTopic={topicFilter}
      />

      <UserProfileDialog
        user={selectedUser}
        isMe={selectedUser?.id === me.id}
        isFollowing={selectedUser ? social.following.includes(selectedUser.id) : false}
        posts={social.posts}
        comments={social.comments}
        me={me}
        onToggleFollow={(userId) =>
          social.following.includes(userId)
            ? social.unfollowUser(userId)
            : social.followUser(userId)
        }
        onOpenPost={onOpenPostFromProfile}
        onClose={() => setProfileUser(null)}
      />
    </div>
  );
}

type Social = ReturnType<typeof useSocial>;