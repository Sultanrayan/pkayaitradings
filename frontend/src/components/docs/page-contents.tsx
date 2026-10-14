"use client";

import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "cn";

export interface PageContentsItem {
  id: string;
  label: string;
}

export interface PageContentsProps {
  items: PageContentsItem[];
  className?: string;
}

/** Offset from the viewport top at which a section counts as "current". */
const OBSERVER_MARGIN = "-88px 0px -70% 0px";

/**
 * Section navigation for the current page.
 *
 * The active entry follows the article through an `IntersectionObserver` rather than
 * a scroll listener, so it costs nothing while the reader is idle. Clicks are handled
 * in JavaScript to get smooth scrolling plus a URL fragment without the browser's
 * instant jump.
 *
 * Below `xl` the same list collapses behind a disclosure, since there is no room for
 * a second column.
 */
export function PageContents({ items, className }: PageContentsProps) {
  const [activeId, setActiveId] = useState(items[0]?.id ?? "");
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActiveId(visible[0].target.id);
      },
      { rootMargin: OBSERVER_MARGIN, threshold: 0 },
    );

    for (const item of items) {
      const element = document.getElementById(item.id);
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
  }, [items]);

  const jumpTo = (event: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    const target = document.getElementById(id);
    if (!target) return;
    event.preventDefault();
    target.scrollIntoView({ behavior: "smooth", block: "start" });
    window.history.replaceState(null, "", `#${id}`);
    setOpen(false);
  };

  const list = (
    <ul className="space-y-2 border-l border-border text-sm">
      {items.map((item) => {
        const active = item.id === activeId;
        return (
          <li key={item.id}>
            <a
              href={`#${item.id}`}
              onClick={(event) => jumpTo(event, item.id)}
              aria-current={active ? "location" : undefined}
              className={cn(
                "-ml-px block border-l-2 py-0.5 pl-3 transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                active
                  ? "border-foreground font-medium text-foreground"
                  : "border-transparent text-muted-foreground",
              )}
            >
              {item.label}
            </a>
          </li>
        );
      })}
    </ul>
  );

  return (
    <nav
      id="page-contents"
      aria-label="Page contents"
      className={cn("sticky top-20", className)}
    >
      <div className="xl:hidden">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          className="flex w-full items-center justify-between rounded-md border border-border px-4 py-2.5 text-sm font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          Page Contents
          <ChevronDown
            aria-hidden
            className={cn("size-4 shrink-0 transition-transform duration-150", open && "rotate-180")}
          />
        </button>
        {open ? <div className="mt-3">{list}</div> : null}
      </div>

      <div className="hidden xl:block">
        <p className="mb-3 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
          Page Contents
        </p>
        {list}
      </div>
    </nav>
  );
}