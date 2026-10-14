"use client";

import Link from "next/link";
import { Check, ChevronDown } from "lucide-react";

import { DOCS_SECTIONS, type DocsSection, type SidebarGroup } from "@/components/docs/docs-sections";
import { SidebarSection } from "@/components/docs/sidebar-section";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "cn";

export interface DocumentationSidebarProps {
  section: DocsSection;
  groups: SidebarGroup[];
  /** Title of the group holding the current page. */
  activeGroup?: string;
  className?: string;
}

/**
 * Documentation sidebar body, shared by the docked rail and the mobile drawer so the
 * two cannot drift apart.
 *
 * The rail scrolls independently of the page, which is what keeps it usable on a long
 * taxonomy without stealing vertical space from the article.
 *
 * The padding is `px-4 sm:px-6` to match the navbar's gutter, so the section selector
 * lines up with the product mark above it.
 */
export function DocumentationSidebar({
  section,
  groups,
  activeGroup,
  className,
}: DocumentationSidebarProps) {
  return (
    <div className={cn("flex h-full flex-col", className)}>
      <div className="border-b border-border px-4 py-3 sm:px-6">
        <DropdownMenu>
          <DropdownMenuTrigger
            aria-label="Documentation section"
            className="flex h-8 w-full items-center gap-2 rounded-md border border-border bg-background px-2.5 text-sm font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-muted"
          >
            <span className="min-w-0 truncate">{section.label}</span>
            <ChevronDown aria-hidden className="ml-auto size-3.5 shrink-0 text-muted-foreground" />
          </DropdownMenuTrigger>

          <DropdownMenuContent align="start" className="w-56">
            {DOCS_SECTIONS.map((entry) => (
              <DropdownMenuItem key={entry.id} asChild>
                <Link
                  href={entry.href}
                  className={cn(
                    "flex-col items-start gap-0.5",
                    entry.id === section.id && "font-medium",
                  )}
                >
                  <span className="flex w-full items-center gap-2">
                    {entry.label}
                    {entry.id === section.id ? <Check aria-hidden className="ml-auto size-4 shrink-0" /> : null}
                  </span>
                  <span className="text-xs text-muted-foreground">{entry.description}</span>
                </Link>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <nav
        aria-label="Documentation"
        className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-4 sm:px-6"
      >
        <ul>
          {groups.map((group) => (
            <SidebarSection
              key={group.title}
              title={group.title}
              items={group.items}
              activeGroup={group.title === activeGroup}
            />
          ))}
        </ul>
      </nav>
    </div>
  );
}