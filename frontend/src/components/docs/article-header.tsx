"use client";

import { Link2 } from "lucide-react";

import { Breadcrumbs, type BreadcrumbItem } from "@/components/docs/breadcrumbs";
import { cn } from "cn";

export interface ArticleHeaderProps {
  breadcrumbs: BreadcrumbItem[];
  category: string;
  title: string;
  /** Compact metadata line: read time, updated date, contents link. */
  readTime: string;
  updatedAt: string;
  /** Anchor id of the page-contents block, linked from the metadata row. */
  contentsHref?: string;
  className?: string;
}

/**
 * Category label, title and metadata above the article body.
 *
 * The heading carries the section anchor id so the page-contents links have
 * something to target.
 */
export function ArticleHeader({
  breadcrumbs,
  category,
  title,
  readTime,
  updatedAt,
  contentsHref = "#page-contents",
  className,
}: ArticleHeaderProps) {
  return (
    <header className={cn("mb-9", className)}>
      <Breadcrumbs items={breadcrumbs} />

      <p className="mt-7 text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
        {category}
      </p>

      <h1 className="mt-2.5 scroll-mt-20 text-[1.75rem] font-semibold tracking-tight text-balance sm:text-4xl">
        {title}
      </h1>

      <div className="mt-4 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-xs text-muted-foreground">
        <span>{readTime}</span>
        <span aria-hidden className="text-border">
          &middot;
        </span>
        <span>{updatedAt}</span>
        <span aria-hidden className="text-border">
          &middot;
        </span>
        <a
          href={contentsHref}
          className="inline-flex items-center gap-1 rounded transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Link2 className="size-3.5" />
          Page Contents
        </a>
      </div>
    </header>
  );
}