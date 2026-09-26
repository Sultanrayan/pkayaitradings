"use client";

import { useState } from "react";
import {
  HeartIcon,
  ImageIcon,
  MessageCircleIcon,
  MoreHorizontalIcon,
  SendIcon,
} from "lucide-react";
import { cn } from "cn";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { formatDateTime } from "@/lib/format";
import type {
  CommunityAuthor,
  CommunityPost,
} from "@/hooks/use-community";

function AuthorAvatar({ author, className }: { author: CommunityAuthor; className?: string }) {
  const initials = author.name
    .split(/\s+/)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  return (
    <Avatar className={className}>
      {author.avatar ? <AvatarImage src={author.avatar} alt={author.name} /> : null}
      <AvatarFallback>{initials || "U"}</AvatarFallback>
    </Avatar>
  );
}

/** Highlight `#tag` tokens in a caption like the reference card does. */
function CaptionText({ caption, hashtags }: { caption: string; hashtags: string[] }) {
  const tokens = caption.split(/(\s+)/);
  const tagSet = new Set(hashtags.map((tag) => `#${tag.toLowerCase()}`));
  return (
    <>
      {tokens.map((token, index) => {
        if (token.startsWith("#")) {
          const isKnown = tagSet.has(token.toLowerCase());
          return (
            <span key={index} className={cn("text-blue-500", !isKnown && "opacity-80")}>
              {token}
            </span>
          );
        }
        return <span key={index}>{token}</span>;
      })}
    </>
  );
}

function CommentRow({ comment }: { comment: CommunityPost["comments"][number] }) {
  return (
    <div className="flex gap-2.5">
      <AuthorAvatar author={comment.author} className="mt-0.5 size-6" />
      <div className="min-w-0 flex-1 rounded-lg bg-muted/60 px-3 py-2">
        <div className="flex items-baseline gap-2">
          <span className="text-xs font-medium">{comment.author.name}</span>
          <span className="text-[10px] text-muted-foreground">
            @{comment.author.handle} · {formatDateTime(comment.createdAt)}
          </span>
        </div>
        <p className="mt-0.5 text-sm text-foreground/85">{comment.text}</p>
      </div>
    </div>
  );
}

/**
 * Community post card styled after 21st.dev card-06 (Post Card): avatar and
 * handle header, 14:9 media, title + caption with hashtags, and action row
 * with Like / Comment / Share. Toggling Comment expands threaded replies.
 */
export function CommunityPostCard({
  post,
  currentUser,
  onToggleLike,
  onAddComment,
}: {
  post: CommunityPost;
  currentUser: CommunityAuthor | null;
  onToggleLike: (postId: string) => void;
  onAddComment: (postId: string, author: CommunityAuthor, text: string) => void;
}) {
  const [commentsOpen, setCommentsOpen] = useState(false);
  const [draft, setDraft] = useState("");

  const handleSubmit = () => {
    if (!draft.trim()) return;
    const author: CommunityAuthor = currentUser ?? {
      name: "Guest Trader",
      handle: "guest",
      avatar: null,
    };
    onAddComment(post.id, author, draft);
    setDraft("");
  };

  return (
    <Card className="w-full gap-0 py-0 ring-border">
      {/* Header: avatar + name + handle + menu */}
      <CardHeader className="-mb-1 flex flex-row items-center justify-between gap-2 px-4 pt-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <AuthorAvatar author={post.author} />
          <div className="min-w-0">
            <div className="truncate text-sm font-medium leading-tight">{post.author.name}</div>
            <div className="text-xs text-muted-foreground">
              @{post.author.handle} · {formatDateTime(post.createdAt)}
            </div>
          </div>
        </div>
        <Button size="icon" variant="ghost" className="shrink-0 text-muted-foreground">
          <MoreHorizontalIcon />
        </Button>
      </CardHeader>

      {/* Media */}
      <div className="relative aspect-[14/9] w-full border-y border-border bg-muted/40">
        {post.image ? (
          // user-supplied images may be data-URLs or remote, so a plain img is used
          // eslint-disable-next-line @next/next/no-img-element
          <img
            alt={post.title || post.caption}
            className="size-full object-cover"
            src={post.image}
          />
        ) : (
          <div className="flex size-full flex-col items-center justify-center gap-1 text-muted-foreground">
            <ImageIcon className="size-8" />
            <span className="text-xs">No image</span>
          </div>
        )}
      </div>

      {/* Text */}
      <CardContent className="gap-0 px-4 py-3">
        {post.title ? <h2 className="font-semibold leading-snug">{post.title}</h2> : null}
        <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
          <CaptionText caption={post.caption} hashtags={post.hashtags} />
        </p>
      </CardContent>

      {/* Actions */}
      <CardFooter className="items-center justify-between border-t px-1 py-0">
        <div className="flex w-full items-center justify-around py-1">
          <Button
            variant="ghost"
            className={cn(
              "shrink-0 text-muted-foreground",
              post.likedByMe && "text-bull",
            )}
            onClick={() => onToggleLike(post.id)}
            aria-pressed={post.likedByMe}
          >
            <HeartIcon className={cn(post.likedByMe && "fill-bull")} />
            <span className="hidden sm:inline">{post.likedByMe ? "Liked" : "Like"}</span>
            {post.likes > 0 ? <span className="tabular">{post.likes}</span> : null}
          </Button>
          <Button
            variant="ghost"
            className="shrink-0 text-muted-foreground"
            onClick={() => {
              setCommentsOpen((open) => !open);
              if (!commentsOpen) setDraft("");
            }}
            aria-expanded={commentsOpen}
          >
            <MessageCircleIcon />
            <span className="hidden sm:inline">Comment</span>
            {post.comments.length > 0 ? (
              <span className="tabular">{post.comments.length}</span>
            ) : null}
          </Button>
          <Button variant="ghost" className="shrink-0 text-muted-foreground">
            <span className="text-base leading-none">↗</span>
            <span className="hidden sm:inline">Share</span>
          </Button>
        </div>
      </CardFooter>

      {/* Comments */}
      {commentsOpen ? (
        <div className="space-y-3 border-t border-border bg-muted/20 px-4 py-3">
          {post.comments.length === 0 ? (
            <p className="text-xs text-muted-foreground">No comments yet — start the thread.</p>
          ) : (
            post.comments.map((comment) => <CommentRow key={comment.id} comment={comment} />)
          )}
          <div className="flex items-center gap-2">
            <AuthorAvatar
              author={currentUser ?? { name: "Guest", handle: "guest", avatar: null }}
              className="size-6"
            />
            <Input
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder="Write a comment…"
              className="h-8 text-sm"
            />
            <Button size="icon-sm" variant="secondary" onClick={handleSubmit} disabled={!draft.trim()}>
              <SendIcon />
              <span className="sr-only">Post comment</span>
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}