"use client";

import { useMemo, useState, useSyncExternalStore } from "react";
import { useRouter } from "next/navigation";
import { CornerDownLeft, Search } from "lucide-react";

import { ENDPOINT_INDEX } from "@/components/docs/docs-endpoints";
import { SEARCH_INDEX, type SearchGroupEntry } from "@/components/docs/docs-search-data";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { cn } from "cn";

type Result = SearchGroupEntry;

/** Group display order in the palette. */
const GROUP_ORDER = ["Documentation", "API Endpoints", "Guides", "Examples"];

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

export interface DocsSearchProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Command-palette search across the documentation.
 *
 * Results are grouped by kind and matched against label plus keywords, so "candle"
 * finds the candle endpoint and the examples that call it. Arrow keys move the
 * highlight and Enter navigates; the highlight index refers to the flat list, so the
 * highlighted row is always the visually highlighted one regardless of grouping.
 */
export function DocsSearch({ open, onOpenChange }: DocsSearchProps) {
  const router = useRouter();
  const modifier = useSyncExternalStore(subscribe, detectModifier, () => "Ctrl");
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const all = useMemo<SearchGroupEntry[]>(
    () => [
      ...SEARCH_INDEX.documentation,
      ...ENDPOINT_INDEX,
      ...SEARCH_INDEX.guides,
      ...SEARCH_INDEX.examples,
    ],
    [],
  );

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return all.slice(0, 12);
    return all
      .filter((entry) =>
        `${entry.label} ${entry.group} ${entry.keywords ?? ""}`.toLowerCase().includes(needle),
      )
      .slice(0, 20);
  }, [all, query]);

  // Keep the highlight inside the list as it shrinks with the query. Done in the
  // change handlers rather than an effect, so no render cascades.
  const onQueryChange = (value: string) => {
    setQuery(value);
    setActive(0);
  };

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setQuery("");
      setActive(0);
    }
    onOpenChange(next);
  };

  // Defensive clamp: if the list shrinks for any other reason, never highlight past
  // its end.
  const activeIndex = Math.min(active, Math.max(results.length - 1, 0));

  const go = (result: Result | undefined) => {
    if (!result) return;
    handleOpenChange(false);
    router.push(result.href);
    if (result.hash) {
      // The anchor may not exist until the route has rendered.
      window.setTimeout(() => {
        document.getElementById(result.hash!)?.scrollIntoView({ behavior: "smooth" });
      }, 150);
    }
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((value) => Math.min(value + 1, results.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((value) => Math.max(value - 1, 0));
    } else if (event.key === "Enter") {
      event.preventDefault();
      go(results[activeIndex]);
    }
  };

  const grouped = useMemo(() => {
    const map = new Map<string, { result: Result; index: number }[]>();
    results.forEach((result, index) => {
      map.set(result.group, [...(map.get(result.group) ?? []), { result, index }]);
    });
    return [...map.entries()].sort(
      (a, b) => GROUP_ORDER.indexOf(a[0]) - GROUP_ORDER.indexOf(b[0]),
    );
  }, [results]);

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent showCloseButton={false} className="gap-0 overflow-hidden p-0 sm:max-w-xl">
        <DialogTitle className="sr-only">Search documentation</DialogTitle>
        <DialogDescription className="sr-only">
          Search the documentation, API endpoints, guides and examples.
        </DialogDescription>

        <div className="flex items-center gap-2 border-b border-border px-3">
          <Search aria-hidden className="size-4 shrink-0 text-muted-foreground" />
          <input
            autoFocus
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search documentation..."
            aria-label="Search documentation"
            className="h-11 min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <kbd className="shrink-0 rounded border border-border bg-muted px-1.5 py-0.5 font-sans text-[10px] leading-none text-muted-foreground">
            {modifier} K
          </kbd>
        </div>

        <div className="max-h-80 overflow-y-auto p-2">
          {results.length === 0 ? (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">
              No results for &ldquo;{query}&rdquo;
            </p>
          ) : (
            grouped.map(([group, entries]) => (
              <div key={group} className="mb-2 last:mb-0">
                <p className="px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-muted-foreground/70">
                  {group}
                </p>
                <ul>
                  {entries.map(({ result, index }) => (
                    <li key={`${group}-${result.label}`}>
                      <button
                        type="button"
                        onClick={() => go(result)}
                        onMouseEnter={() => setActive(index)}
                        className={cn(
                          "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors",
                          index === active
                            ? "bg-muted text-foreground"
                            : "text-muted-foreground hover:text-foreground",
                        )}
                      >
                        <span className="min-w-0 flex-1 truncate">{result.label}</span>
                        {index === active ? (
                          <CornerDownLeft aria-hidden className="size-3.5 shrink-0" />
                        ) : null}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}