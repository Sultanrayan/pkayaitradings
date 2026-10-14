"use client";

import Link from "next/link";

import type { SidebarItem } from "@/components/docs/docs-sections";
import { cn } from "cn";

export interface SidebarSectionProps {
  title: string;
  items: SidebarItem[];
  /** The current page lives in this group. */
  activeGroup?: boolean;
  className?: string;
}

/**
 * One group in the documentation sidebar.
 *
 * The heading is a non-interactive uppercase label rather than the previous
 * collapsible disclosure: these groups are short, fixed taxonomies, and a list that
 * can hide entries is worse in a sidebar you scan than one that is always visible.
 * The label still identifies the active group so the reader's position is obvious.
 */
export function SidebarSection({ title, items, activeGroup, className }: SidebarSectionProps) {
  return (
    <li className={cn("py-3 first:pt-0", className)}>
      <h3
        className={cn(
          "mb-1.5 px-2 text-[11px] font-medium uppercase tracking-[0.08em]",
          activeGroup ? "text-foreground" : "text-muted-foreground/70",
        )}
      >
        {title}
      </h3>

      <ul className="space-y-px">
        {items.map((item) => {
          const active = Boolean(item.active);
          const internal = item.href.startsWith("#");
          const className = cn(
            "block rounded-md px-2 py-1 text-[13px] leading-5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
            active
              ? "bg-muted font-medium text-foreground"
              : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
          );

          return (
            <li key={item.label}>
              {internal ? (
                <a href={item.href} aria-current={active ? "page" : undefined} className={className}>
                  {item.label}
                </a>
              ) : (
                <Link href={item.href} aria-current={active ? "page" : undefined} className={className}>
                  {item.label}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </li>
  );
}