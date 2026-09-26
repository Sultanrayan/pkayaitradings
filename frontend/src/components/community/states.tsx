"use client";

import { RefreshCcwIcon } from "lucide-react";
import { cn } from "cn";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

/** Skeleton feed of post cards while posts load. */
export function PostSkeletons({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, index) => (
        <Card key={index} className="gap-0 p-4 ring-border">
          <div className="flex items-center gap-3">
            <Skeleton className="size-10 rounded-full bg-muted" />
            <div className="space-y-2">
              <Skeleton className="h-3 w-32 bg-muted" />
              <Skeleton className="h-2.5 w-24 bg-muted" />
            </div>
          </div>
          <div className="mt-4 space-y-2">
            <Skeleton className="h-3 w-full bg-muted" />
            <Skeleton className="h-3 w-4/5 bg-muted" />
          </div>
          <Skeleton className="mt-4 h-28 w-full rounded-lg bg-muted" />
        </Card>
      ))}
    </div>
  );
}

/** Skeleton for the compact right-sidebar cards. */
export function SidebarSkeletons() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 3 }).map((_, index) => (
        <div key={index} className="space-y-2 rounded-xl border border-border bg-card p-3">
          <Skeleton className="h-3 w-28 bg-muted" />
          {Array.from({ length: 3 }).map((__, child) => (
            <div key={child} className="flex items-center gap-2">
              <Skeleton className="size-6 rounded-full bg-muted" />
              <Skeleton className="h-3 flex-1 bg-muted" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

/** Empty-state used for empty feeds and sidebar sections. */
export function EmptyFeed({
  title,
  hint,
  actionLabel,
  onAction,
  className,
}: {
  title: string;
  hint?: string;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
}) {
  return (
    <Card className={cn("p-6 text-center ring-border", className)}>
      <p className="text-sm font-medium">{title}</p>
      {hint ? <p className="mt-1 text-xs text-muted-foreground">{hint}</p> : null}
      {actionLabel && onAction ? (
        <Button variant="outline" size="sm" className="mt-3" onClick={onAction}>
          {actionLabel}
        </Button>
      ) : null}
    </Card>
  );
}

/** Error state with retry — never breaks the whole page. */
export function FeedError({
  message = "Unable to load community posts.",
  onRetry,
}: {
  message?: string;
  onRetry: () => void;
}) {
  return (
    <Card className="p-6 text-center ring-border">
      <p className="text-sm font-medium text-bear">{message}</p>
      <Button variant="outline" size="sm" className="mt-3 gap-1.5" onClick={onRetry}>
        <RefreshCcwIcon className="size-3.5" /> Try again
      </Button>
    </Card>
  );
}