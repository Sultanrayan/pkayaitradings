"use client";

import { useState } from "react";
import {
  BookmarkIcon,
  HeartIcon,
  MessageCircleIcon,
  MoreHorizontalIcon,
  RepeatIcon,
  SendIcon,
  ShareIcon,
} from "lucide-react";
import { cn } from "cn";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export interface PostCounts {
  likes: number;
  comments: number;
  reposts: number;
}

export function PostActions({
  liked,
  reposted,
  bookmarked,
  counts,
  onLike,
  onComment,
  onRepost,
  onQuote,
  onShare,
  onBookmark,
}: {
  liked: boolean;
  reposted: boolean;
  bookmarked: boolean;
  counts: PostCounts;
  onLike: () => void;
  onComment: () => void;
  onRepost: () => void;
  onQuote: () => void;
  onShare: () => void;
  onBookmark: () => void;
}) {
  return (
    <div className="flex max-w-md items-center justify-between gap-1 py-1">
      {/* Like */}
      <ActionButton
        label={counts.likes > 0 ? String(counts.likes) : "Like"}
        icon={<HeartIcon className={cn("size-[18px]")} />}
        active={liked}
        activeClass="text-bull [&_svg]:fill-bull"
        onClick={onLike}
      />
      {/* Comment */}
      <ActionButton
        label={counts.comments > 0 ? String(counts.comments) : "Comment"}
        icon={<MessageCircleIcon className="size-[18px]" />}
        active={false}
        onClick={onComment}
      />
      {/* Repost / share menu */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
              reposted && "text-bull",
            )}
          >
            <RepeatIcon className={cn("size-[18px]", reposted && "text-bull")} />
            {reposted ? "Reposted" : counts.reposts > 0 ? String(counts.reposts) : "Repost"}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side="top">
          <DropdownMenuItem onClick={onRepost}>Repost</DropdownMenuItem>
          <DropdownMenuItem onClick={onQuote}>Quote post</DropdownMenuItem>
          <DropdownMenuItem onClick={onShare}>Send via…</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <ActionButton
        label="Share"
        icon={<ShareIcon className="size-[18px]" />}
        active={false}
        onClick={onShare}
      />
      <ActionButton
        label={bookmarked ? "Saved" : "Save"}
        icon={<BookmarkIcon className={cn("size-[18px]", bookmarked && "fill-gold text-gold")} />}
        active={bookmarked}
        activeClass="text-gold"
        onClick={onBookmark}
      />
    </div>
  );
}

function ActionButton({
  label,
  icon,
  active,
  activeClass,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  active: boolean;
  activeClass?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
        active && activeClass,
      )}
    >
      {icon}
      {label}
    </button>
  );
}

export function MoreMenu({
  saved,
  muted,
  blocked,
  onSave,
  onCopyLink,
  onReport,
  onMute,
  onBlock,
  onAnalyze,
}: {
  saved: boolean;
  muted: boolean;
  blocked: boolean;
  onSave: () => void;
  onCopyLink: () => void;
  onReport: () => void;
  onMute: () => void;
  onBlock: () => void;
  onAnalyze: () => void;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="icon-sm" variant="ghost" className="text-muted-foreground">
          <MoreHorizontalIcon className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={onSave}>{saved ? "Unsave post" : "Save post"}</DropdownMenuItem>
        <DropdownMenuItem onClick={onAnalyze}>Analyze with AI</DropdownMenuItem>
        <DropdownMenuItem
          onClick={() => {
            onCopyLink();
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          }}
        >
          {copied ? "Copied!" : "Copy link"}
        </DropdownMenuItem>
        <DropdownMenuItem variant="destructive" onClick={onReport}>
          Report
        </DropdownMenuItem>
        <DropdownMenuItem onClick={onMute}>{muted ? "Unmute user" : "Mute user"}</DropdownMenuItem>
        <DropdownMenuItem variant="destructive" onClick={onBlock}>
          {blocked ? "Unblock user" : "Block user"}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function InlineReplyComposer({
  onSubmit,
  placeholder = "Write a reply…",
}: {
  onSubmit: (text: string) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState("");
  const submit = () => {
    if (!draft.trim()) return;
    onSubmit(draft);
    setDraft("");
  };
  return (
    <div className="flex items-center gap-2">
      <input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            submit();
          }
        }}
        placeholder={placeholder}
        className="h-8 w-full min-w-0 rounded-full border border-border bg-muted/40 px-3 text-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      />
      <Button size="icon-sm" variant="secondary" onClick={submit} disabled={!draft.trim()}>
        <SendIcon className="size-3.5" />
        <span className="sr-only">Send</span>
      </Button>
    </div>
  );
}