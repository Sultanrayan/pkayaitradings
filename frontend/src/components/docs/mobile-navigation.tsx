"use client";

import { useEffect } from "react";
import { Menu, X } from "lucide-react";

import { DocumentationSidebar } from "@/components/docs/documentation-sidebar";
import type { DocsSection, SidebarGroup } from "@/components/docs/docs-sections";

export interface MobileNavigationProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  section: DocsSection;
  groups: SidebarGroup[];
  activeGroup?: string;
}

/**
 * Slide-out documentation drawer for small screens.
 *
 * Reached from the navbar's menu button. The panel is `fixed` so it overlays the
 * article rather than displacing it, closes on Escape, and locks background scroll
 * while open so the page behind cannot move under the overlay.
 */
export function MobileNavigation({
  open,
  onOpenChange,
  section,
  groups,
  activeGroup,
}: MobileNavigationProps) {
  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    document.addEventListener("keydown", onKeyDown);

    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previous;
    };
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 top-14 z-40 lg:hidden">
      <button
        type="button"
        aria-label="Close navigation"
        onClick={() => onOpenChange(false)}
        className="absolute inset-0 bg-background/60 backdrop-blur-sm"
      />

      <div className="relative flex h-full w-[min(20rem,85vw)] flex-col border-r border-border bg-background">
        <div className="flex items-center justify-between border-b border-border px-4 py-3 sm:px-6">
          <span className="text-sm font-medium">Documentation</span>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            aria-label="Close navigation"
            className="grid size-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="size-4" />
          </button>
        </div>

        <DocumentationSidebar
          section={section}
          groups={groups}
          activeGroup={activeGroup}
          className="min-h-0 flex-1"
        />
      </div>
    </div>
  );
}

/** Menu button that opens {@link MobileNavigation}; lives in the navbar. */
export function MobileNavigationTrigger({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Open navigation"
      className="grid size-9 shrink-0 place-items-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:hidden"
    >
      <Menu className="size-4" />
    </button>
  );
}