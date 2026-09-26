"use client";

import { useMemo, useState } from "react";
import { CalendarIcon, UserCheckIcon, UserPlusIcon } from "lucide-react";
import { cn } from "cn";

import { UserAvatar, VerifiedBadge, relativeTime } from "@/components/community/shared";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { SocialComment, SocialPost, SocialUser } from "@/hooks/use-social";

type ProfileTab = "posts" | "replies" | "media" | "saved";

/**
 * User profile modal opened from any avatar / username click. Shows bio,
 * follower/following counts, join date and tabbed content (posts, replies,
 * media, saved discussions).
 */
export function UserProfileDialog({
  user,
  isMe,
  isFollowing,
  posts,
  comments,
  me,
  onToggleFollow,
  onOpenPost,
  onClose,
}: {
  user: SocialUser | null;
  isMe: boolean;
  isFollowing: boolean;
  posts: SocialPost[];
  comments: SocialComment[];
  me: SocialUser;
  onToggleFollow: (userId: string) => void;
  onOpenPost: (postId: string) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<ProfileTab>("posts");

  const userPosts = useMemo(
    () => (user ? posts.filter((post) => post.authorId === user.id) : []),
    [posts, user],
  );
  const userReplies = useMemo(
    () => (user ? comments.filter((comment) => comment.authorId === user.id) : []),
    [comments, user],
  );
  const userMedia = useMemo(
    () =>
      userPosts.filter((post) =>
        post.attachments.some((attachment) => attachment.type === "image"),
      ),
    [userPosts],
  );
  const saved = useMemo(() => posts.filter((post) => post.savedByMe), [posts]);
  const joinDate = useMemo(
    () =>
      user
        ? new Date(user.joinedAt).toLocaleDateString("en-US", {
            month: "long",
            year: "numeric",
          })
        : "",
    [user],
  );
  const currentList = useMemo(() => {
    if (tab === "posts") return userPosts;
    if (tab === "media") return userMedia;
    if (tab === "saved") return saved;
    return [];
  }, [tab, userPosts, userMedia, saved]);
  const empty = useMemo(() => {
    if (tab === "posts") return userPosts.length === 0;
    if (tab === "replies") return userReplies.length === 0;
    if (tab === "media") return userMedia.length === 0;
    return saved.length === 0;
  }, [tab, userPosts, userReplies, userMedia, saved]);

  if (!user) return null;

  const tabs: Array<{ key: ProfileTab; label: string; count?: number }> = [
    { key: "posts", label: "Posts", count: userPosts.length },
    { key: "replies", label: "Replies", count: userReplies.length },
    { key: "media", label: "Media", count: userMedia.length },
    { key: "saved", label: "Saved", count: me.id === user.id ? saved.length : undefined },
  ];

  return (
    <Dialog open onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="max-w-lg gap-0 overflow-hidden bg-card p-0 sm:max-w-lg">
        {/* Banner */}
        <div className="h-28 bg-gradient-to-r from-muted via-accent to-muted" />
        <DialogHeader className="px-4 pb-2">
          <div className="-mt-10 flex items-end justify-between">
            <UserAvatar user={user} size="lg" className="ring-4 ring-card" />
            {!isMe ? (
              <Button
                variant={isFollowing ? "outline" : "default"}
                size="sm"
                className="gap-1"
                onClick={() => onToggleFollow(user.id)}
              >
                {isFollowing ? (
                  <UserCheckIcon className="size-3.5" />
                ) : (
                  <UserPlusIcon className="size-3.5" />
                )}
                {isFollowing ? "Following" : "Follow"}
              </Button>
            ) : null}
          </div>
          <DialogTitle className="mt-2 flex items-center gap-1.5">
            <span className="text-lg">{user.name}</span>
            {user.verified ? <VerifiedBadge /> : null}
          </DialogTitle>
          <div className="text-sm text-muted-foreground">@{user.handle}</div>
        </DialogHeader>

        <div className="space-y-3 px-4 pb-4">
          <p className="text-sm text-muted-foreground">{user.bio}</p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <CalendarIcon className="size-3.5" /> Joined {joinDate}
            </span>
            <span>
              <span className="font-semibold text-foreground tabular">
                {user.followers.toLocaleString()}
              </span>{" "}
              Followers
            </span>
            <span>
              <span className="font-semibold text-foreground tabular">
                {user.following.toLocaleString()}
              </span>{" "}
              Following
            </span>
          </div>

          {/* Tabs */}
          <div className="flex divide-x divide-border overflow-x-auto rounded-lg border border-border">
            {tabs.map((item) => (
              <button
                key={item.key}
                type="button"
                onClick={() => setTab(item.key)}
                className={cn(
                  "flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap px-2 py-2 text-xs font-medium text-muted-foreground transition-colors",
                  tab === item.key && "bg-accent text-foreground",
                )}
              >
                {item.label}
                {typeof item.count === "number" ? (
                  <span className="tabular text-[10px]">{item.count}</span>
                ) : null}
              </button>
            ))}
          </div>

          <div className="max-h-80 space-y-2 overflow-y-auto">
            {tab === "replies"
              ? userReplies.map((reply) => (
                  <div key={reply.id} className="rounded-lg border border-border px-3 py-2">
                    <p className="line-clamp-2 text-xs text-foreground/85">{reply.text}</p>
                    <div className="mt-1 text-[10px] text-muted-foreground">
                      {relativeTime(reply.createdAt)} · reply
                    </div>
                  </div>
                ))
              : currentList.map((post) => (
                  <button
                    key={post.id}
                    type="button"
                    onClick={() => onOpenPost(post.id)}
                    className="block w-full rounded-lg border border-border px-3 py-2 text-left transition-colors hover:bg-accent/40"
                  >
                    <div className="line-clamp-2 text-xs text-foreground/85">
                      {post.text || "Attachment post"}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[10px] text-muted-foreground">
                      <span className="truncate font-medium text-blue-500">
                        {post.hashtags.map((tag) => `#${tag}`).join(" ")}
                      </span>
                      <span className="ml-auto shrink-0 tabular">
                        {relativeTime(post.createdAt)}
                      </span>
                    </div>
                  </button>
                ))}
            {empty ? (
              <p className="py-6 text-center text-xs text-muted-foreground">
                {tab === "saved" ? "No saved discussions yet." : "Nothing here yet."}
              </p>
            ) : null}
          </div>
        </div>

        <div className="px-4 pb-4">
          <Card className="ring-border">
            <CardHeader className="pb-2">
              <CardTitle className="text-xs">About</CardTitle>
            </CardHeader>
            <CardContent className="px-4 pb-3">
              <p className="text-xs text-muted-foreground">
                {user.bio}
                {user.verified ? " · Verified trader" : ""}
              </p>
            </CardContent>
          </Card>
        </div>
      </DialogContent>
    </Dialog>
  );
}