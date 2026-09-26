"use client";

import { useMemo, useState } from "react";
import { MessageCircleIcon, UserPlusIcon, UserCheckIcon } from "lucide-react";
import { cn } from "cn";

import {
  ChartAttachment,
  MarketAttachment,
  SignalAttachment,
} from "@/components/community/attachments";
import { CommentThread } from "@/components/community/comment-thread";
import { MoreMenu, PostActions } from "@/components/community/post-actions";
import { UserAvatar, VerifiedBadge, relativeTime } from "@/components/community/shared";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
} from "@/components/ui/card";
import type {
  PostAttachment,
  SocialComment,
  SocialPost,
  SocialUser,
} from "@/hooks/use-social";

const SHOW_MORE = 220;

function AttachmentList({
  attachments,
  onOpenMarket,
}: {
  attachments: PostAttachment[];
  onOpenMarket: (symbol: string) => void;
}) {
  const images = attachments.filter((attachment) => attachment.type === "image");
  const videos = attachments.filter((attachment) => attachment.type === "video");
  const markets = attachments.filter((attachment) => attachment.type === "market");
  const charts = attachments.filter((attachment) => attachment.type === "chart");
  const signals = attachments.filter((attachment) => attachment.type === "signal");

  return (
    <div className="space-y-2">
      {images.length > 0 ? (
        <div
          className={cn(
            "grid gap-1 overflow-hidden rounded-lg border border-border",
            images.length > 1 && "grid-cols-2",
          )}
        >
          {images.map((attachment) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={attachment.id}
              src={attachment.url}
              alt={attachment.alt ?? ""}
              className={cn(
                "size-full object-cover",
                images.length === 1 ? "max-h-72 w-full" : "aspect-square",
              )}
            />
          ))}
        </div>
      ) : null}
      {videos.length > 0 ? (
        <div className="overflow-hidden rounded-lg border border-border">
          {videos.map((attachment) => (
            <video key={attachment.id} src={attachment.url} controls className="max-h-72 w-full bg-black" />
          ))}
        </div>
      ) : null}
      {markets.map((attachment) => (
        <MarketAttachment
          key={attachment.id}
          symbol={attachment.symbol}
          onClick={() => onOpenMarket(attachment.symbol)}
        />
      ))}
      {charts.map((attachment) =>
        attachment.type === "chart" ? (
          <ChartAttachment
            key={attachment.id}
            symbol={attachment.symbol}
            timeframe={attachment.timeframe}
            onClick={() => onOpenMarket(attachment.symbol)}
          />
        ) : null,
      )}
      {signals.map((attachment) =>
        attachment.type === "signal" ? (
          <SignalAttachment
            key={attachment.id}
            symbol={attachment.symbol}
            side={attachment.side}
            timeframe={attachment.timeframe}
            entry={attachment.entry}
            target={attachment.target}
            stop={attachment.stop}
            createdAt={attachment.createdAt}
            onClick={() => onOpenMarket(attachment.symbol)}
          />
        ) : null,
      )}
    </div>
  );
}

function PostText({ text, hashtags }: { text: string; hashtags: string[] }) {
  const [expanded, setExpanded] = useState(false);
  const long = text.length > SHOW_MORE;
  const shown = long && !expanded ? `${text.slice(0, SHOW_MORE)}…` : text;
  const tagSet = new Set(hashtags.map((tag) => tag.toLowerCase()));

  return (
    <div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">
        {shown.split(/(\s+)/).map((token, index) => {
          const isTag = /^#[\w\d_-]+$/.test(token);
          return isTag ? (
            <span key={index} className="text-blue-500">
              {token}
            </span>
          ) : (
            <span key={index}>{token}</span>
          );
        })}
      </p>
      {long ? (
        <button
          type="button"
          onClick={() => setExpanded((value) => !value)}
          className="mt-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          {expanded ? "Show less" : "Show more"}
        </button>
      ) : null}
      {tagSet.size > 0 && !long ? (
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {Array.from(tagSet).map((tag) => (
            <span key={tag} className="text-xs text-blue-500">
              #{tag}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Reusable community post: header (avatar, name, handle, verified, time,
 * follow, more menu), text with show-more, optional attachments (images,
 * video, market, chart, signal), engagement actions and an expandable comment
 * thread.
 */
export function PostCard({
  post,
  author,
  me,
  isFollowing,
  comments,
  onToggleFollow,
  onLike,
  onRepost,
  onBookmark,
  onShare,
  onQuote,
  onSave,
  onCopyLink,
  onReport,
  onMute,
  onBlock,
  onAnalyze,
  onOpenMarket,
  onOpenProfile,
  onAddComment,
  onReplyToComment,
  onToggleCommentLike,
  onToggleCommentRepost,
  onDeleteComment,
  onReportComment,
  usersById,
  defaultThreadOpen = false,
}: {
  post: SocialPost;
  author: SocialUser | undefined;
  me: SocialUser;
  isFollowing: boolean;
  comments: SocialComment[];
  onToggleFollow: (userId: string) => void;
  onLike: (postId: string) => void;
  onRepost: (postId: string) => void;
  onBookmark: (postId: string) => void;
  onShare: (postId: string) => void;
  onQuote: (postId: string) => void;
  onSave: (postId: string) => void;
  onCopyLink: (postId: string) => void;
  onReport: (postId: string) => void;
  onMute: (postId: string) => void;
  onBlock: (postId: string) => void;
  onAnalyze: (postId: string) => void;
  onOpenMarket: (symbol: string) => void;
  onOpenProfile: (userId: string) => void;
  onAddComment: (postId: string, text: string) => void;
  onReplyToComment: (postId: string, commentId: string, text: string) => void;
  onToggleCommentLike: (commentId: string, postId: string) => void;
  onToggleCommentRepost: (commentId: string, postId: string) => void;
  onDeleteComment: (commentId: string, postId: string) => void;
  onReportComment: (commentId: string, postId: string) => void;
  usersById: (id: string) => SocialUser | undefined;
  defaultThreadOpen?: boolean;
}) {
  const [threadOpen, setThreadOpen] = useState(defaultThreadOpen);
  const mine = post.authorId === me.id;

  const commentCount = useMemo(() => comments.length, [comments]);

  return (
    <Card className="w-full gap-0 py-0 ring-border">
      <CardHeader className="-mb-1 flex-row items-center gap-2.5 px-4 pt-3">
        <button type="button" onClick={() => onOpenProfile(post.authorId)}>
          <UserAvatar user={author ?? { name: "Unknown", avatar: null }} />
        </button>
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={() => onOpenProfile(post.authorId)}
            className="flex min-w-0 items-center gap-1 text-left"
          >
            <span className="truncate text-sm font-medium">{author?.name ?? "Unknown"}</span>
            {author?.verified ? <VerifiedBadge /> : null}
          </button>
          <div className="flex items-center gap-1 text-xs text-muted-foreground">
            <span className="truncate">@{author?.handle ?? "unknown"}</span>
            <span>·</span>
            <span>{relativeTime(post.createdAt)}</span>
          </div>
        </div>
        {!mine ? (
          <Button
            size="sm"
            variant={isFollowing ? "outline" : "default"}
            className="gap-1"
            onClick={() => onToggleFollow(post.authorId)}
          >
            {isFollowing ? (
              <>
                <UserCheckIcon className="size-3.5" /> Following
              </>
            ) : (
              <>
                <UserPlusIcon className="size-3.5" /> Follow
              </>
            )}
          </Button>
        ) : null}
        <MoreMenu
          saved={post.savedByMe}
          muted={post.mutedByMe}
          blocked={post.blockedByMe}
          onSave={() => onSave(post.id)}
          onCopyLink={() => onCopyLink(post.id)}
          onReport={() => onReport(post.id)}
          onMute={() => onMute(post.id)}
          onBlock={() => onBlock(post.id)}
          onAnalyze={() => onAnalyze(post.id)}
        />
      </CardHeader>

      <CardContent className="space-y-3 px-4 py-3">
        <PostText text={post.text} hashtags={post.hashtags} />
        <AttachmentList attachments={post.attachments} onOpenMarket={onOpenMarket} />
      </CardContent>

      <CardFooter className="flex-col items-stretch gap-1 border-t px-2 py-0">
        <PostActions
          liked={post.likedByMe}
          reposted={post.repostedByMe}
          bookmarked={post.bookmarkedByMe}
          counts={{
            likes: post.likes,
            comments: commentCount,
            reposts: post.reposts,
          }}
          onLike={() => onLike(post.id)}
          onComment={() => setThreadOpen((value) => !value)}
          onRepost={() => onRepost(post.id)}
          onQuote={() => onQuote(post.id)}
          onShare={() => onShare(post.id)}
          onBookmark={() => onBookmark(post.id)}
        />
        {commentCount > 0 && !threadOpen ? (
          <button
            type="button"
            onClick={() => setThreadOpen(true)}
            className="flex items-center gap-1.5 px-3 py-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          >
            <MessageCircleIcon className="size-3.5" />
            {commentCount} {commentCount === 1 ? "comment" : "comments"}
          </button>
        ) : null}
      </CardFooter>

      {threadOpen ? (
        <CommentThread
          comments={comments}
          me={me}
          usersById={usersById}
          topPlaceholder="Add a comment…"
          onTopReply={(text) => onAddComment(post.id, text)}
          onReplyToComment={(commentId, text) => onReplyToComment(post.id, commentId, text)}
          onLike={(commentId) => onToggleCommentLike(commentId, post.id)}
          onRepost={(commentId) => onToggleCommentRepost(commentId, post.id)}
          onDelete={(commentId) => onDeleteComment(commentId, post.id)}
          onReport={(commentId) => onReportComment(commentId, post.id)}
        />
      ) : null}
    </Card>
  );
}