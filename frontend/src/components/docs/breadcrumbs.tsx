import { ChevronRight } from "lucide-react";

import { cn } from "cn";

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export interface BreadcrumbsProps {
  items: BreadcrumbItem[];
  className?: string;
}

/**
 * Trail above the article title. The final crumb is the current page and is marked
 * `aria-current` rather than being a link.
 */
export function Breadcrumbs({ items, className }: BreadcrumbsProps) {
  return (
    <nav aria-label="Breadcrumb" className={cn("min-w-0", className)}>
      <ol className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
        {items.map((item, index) => {
          const last = index === items.length - 1;
          return (
            <li key={`${item.label}-${index}`} className="flex min-w-0 items-center gap-1">
              {item.href && !last ? (
                <a
                  href={item.href}
                  className="truncate rounded transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {item.label}
                </a>
              ) : (
                <span
                  aria-current={last ? "page" : undefined}
                  className={cn("truncate", last && "text-foreground")}
                >
                  {item.label}
                </span>
              )}
              {!last ? <ChevronRight aria-hidden className="size-3.5 shrink-0 opacity-60" /> : null}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}