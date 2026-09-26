"use client";

import { cn } from "cn";
import type { FeedTab } from "@/hooks/use-social";

const TABS: Array<{ key: FeedTab; label: string }> = [
  { key: "forYou", label: "For You" },
  { key: "following", label: "Following" },
  { key: "trending", label: "Trending" },
];

export function FeedTabs({
  active,
  onChange,
  counts,
}: {
  active: FeedTab;
  onChange: (tab: FeedTab) => void;
  counts?: Partial<Record<FeedTab, number>>;
}) {
  return (
    <div
      role="tablist"
      aria-label="Feed tabs"
      className="flex divide-x divide-border overflow-x-auto rounded-lg border border-border bg-card"
    >
      {TABS.map((tab) => {
        const selected = active === tab.key;
        const count = counts?.[tab.key];
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => onChange(tab.key)}
            className={cn(
              "flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap px-3 py-2 text-sm font-medium text-muted-foreground transition-colors",
              selected && "bg-accent text-foreground",
            )}
          >
            {tab.label}
            {typeof count === "number" ? (
              <span className="tabular text-[11px] text-muted-foreground">{count}</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}