"use client";

import { useMemo, useState } from "react";
import { HeartIcon, MoreHorizontalIcon, RepeatIcon, TrashIcon } from "lucide-react";
import { cn } from "cn";

import { UserAvatar, relativeTime } from "@/components/community/shared";
import { InlineReplyComposer } from "@/components/community/post-actions";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { SocialComment, SocialUser } from "@/hooks/use-social";

function ReplyBody({
  comment,
  author,
  me,
  depth,
  onLike,
  onRepost,
  onReply,
  onDelete,
  onReport,
}: {
  comment: SocialComment;
  author: SocialUser | undefined;
  me: SocialUser;
  depth: number;
  onLike: (id: string) => void;
  onRepost: (id: string) => void;
  onReply: (id: string, text: string) => void;
  onDelete: (id: string) => void;
  onReport: (id: string) => void;
}) {
  const [replying, setReplying] = useState(false);
  const mine = comment.authorId === me.id;
  const deleted = comment.deletedByAuthor;

  return (
    <div className={cn("flex gap-2.5", depth > 0 && "pl-6")}>
      {author ? <UserAvatar user={author} size="sm" className="mt-0.5" /> : null}
      <div className="min-w-0 flex-1">
        <div className="rounded-2xl bg-muted/60 px-3 py-2">
          <div className="flex items-center gap-1.5">
            <span className="text-xs font-medium">
              {deleted ? "Deleted user" : author?.name ?? "Unknown"}
            </span>
            {deleted ? null : (
              <span className="text-[10px] text-muted-foreground">
                @{author?.handle} · {relativeTime(comment.createdAt)}
              </span>
            )}
          </div>
          <p className={cn("mt-0.5 text-sm", deleted && "italic text-muted-foreground")}>
            {deleted ? "This reply was deleted." : comment.text}
          </p>
        </div>

        {deleted ? null : (
          <div className="mt-0.5 flex items-center gap-3 pl-2">
            <button
              type="button"
              onClick={() => onLike(comment.id)}
              className={cn(
                "flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground",
                comment.likedByMe && "text-bull",
              )}
            >
              <HeartIcon className={cn("size-3", comment.likedByMe && "fill-bull")} />
              {comment.likes > 0 ? comment.likes : null}
            </button>
            <button
              type="button"
              onClick={() => onRepost(comment.id)}
              className={cn(
                "flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground",
                comment.repostedByMe && "text-bull",
              )}
            >
              <RepeatIcon className="size-3" />
              {comment.reposts > 0 ? comment.reposts : null}
            </button>
            <button
              type="button"
              onClick={() => setReplying((value) => !value)}
              className="text-[11px] text-muted-foreground transition-colors hover:text-foreground"
            >
              Reply
            </button>

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="icon-xs" variant="ghost" className="ml-auto text-muted-foreground">
                  <MoreHorizontalIcon className="size-3" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => onReport(comment.id)} disabled={comment.reportedByMe}>
                  {comment.reportedByMe ? "Reported" : "Report reply"}
                </DropdownMenuItem>
                {mine ? (
                  <DropdownMenuItem variant="destructive" onClick={() => onDelete(comment.id)}>
                    <TrashIcon className="size-3.5" /> Delete my reply
                  </DropdownMenuItem>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}

        {replying && !deleted ? (
          <div className="mt-2 pl-2">
            <InlineReplyComposer
              placeholder={`Reply to @${author?.handle ?? "post"}…`}
              onSubmit={(text) => {
                onReply(comment.id, text);
                setReplying(false);
              }}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Full comment thread for a post. The original post stays pinned above the
 * thread (handled by the caller); this renders top-level replies plus nested
 * replies one level deep, each with like / repost / reply / report / delete.
 */
export function CommentThread({
  comments,
  me,
  usersById,
  topPlaceholder = "Add a comment…",
  onTopReply,
  onReplyToComment,
  onLike,
  onRepost,
  onDelete,
  onReport,
}: {
  comments: SocialComment[];
  me: SocialUser;
  usersById: (id: string) => SocialUser | undefined;
  topPlaceholder?: string;
  onTopReply: (text: string) => void;
  onReplyToComment: (commentId: string, text: string) => void;
  onLike: (commentId: string) => void;
  onRepost: (commentId: string) => void;
  onDelete: (commentId: string) => void;
  onReport: (commentId: string) => void;
}) {
  const topLevel = useMemo(
    () => comments.filter((comment) => comment.parentId === null),
    [comments],
  );

  // Avoid duplicate rendering when a nested reply is also queried via filter.
  const render = (comment: SocialComment) => {
    const children = comments.filter((c) => c.parentId === comment.id);
    return (
      <div key={comment.id} className="space-y-2">
        <ReplyBody
          comment={comment}
          author={usersById(comment.authorId)}
          me={me}
          depth={0}
          onLike={onLike}
          onRepost={onRepost}
          onReply={(id, text) => onReplyToComment(id, text)}
          onDelete={onDelete}
          onReport={onReport}
        />
        {children.length > 0 ? (
          <div className="space-y-2">
            {children.map((child) => (
              <ReplyBody
                key={child.id}
                comment={child}
                author={usersById(child.authorId)}
                me={me}
                depth={1}
                onLike={onLike}
                onRepost={onRepost}
                onReply={(id, text) => onReplyToComment(id, text)}
                onDelete={onDelete}
                onReport={onReport}
              />
            ))}
          </div>
        ) : null}
      </div>
    );
  };

  return (
    <div className="space-y-3 border-t border-border bg-muted/20 px-4 py-3">
      <InlineReplyComposer placeholder={topPlaceholder} onSubmit={onTopReply} />
      {topLevel.length === 0 ? (
        <p className="text-xs text-muted-foreground">No comments yet — start the discussion.</p>
      ) : (
        <div className="space-y-3">
          {topLevel.map((comment) => render(comment))}
        </div>
      )}
    </div>
  );
}