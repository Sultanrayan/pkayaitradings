"use client";

import { useSyncExternalStore } from "react";
import { Search } from "lucide-react";

import { cn } from "cn";

export interface SearchBarProps {
  className?: string;
  /** Opens the search palette instead of focusing the field inline. */
  onClick?: () => void;
}

/**
 * Platform modifier key, read as external state so the server render and the first
 * client render agree. `navigator.platform` is deprecated, so the user agent is
 * matched; the value cannot change during a session.
 */
const subscribe = () => () => {};
function detectModifier(): string {
  const agent = typeof navigator === "undefined" ? "" : navigator.userAgent;
  return /Mac|iPhone|iPad|iPod/.test(agent) ? "⌘" : "Ctrl";
}

/**
 * Documentation search trigger with the shortcut hint on the trailing edge.
 *
 * Rendered as a button rather than a field: it opens the command palette, which does
 * the actual searching, so presenting it as an inert input would be misleading.
 */
export function SearchBar({ className, onClick }: SearchBarProps) {
  const modifier = useSyncExternalStore(subscribe, detectModifier, () => "Ctrl");

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Search documentation"
      className={cn(
        "h-8 w-full max-w-64 items-center gap-2 rounded-md border border-border bg-background px-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    >
      <Search aria-hidden className="size-3.5 shrink-0" />
      <span className="truncate">Search documentation...</span>
      <kbd className="ml-auto hidden shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 font-sans text-[10px] leading-none text-muted-foreground sm:inline-block">
        {modifier} K
      </kbd>
    </button>
  );
}