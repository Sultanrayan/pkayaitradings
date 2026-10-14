"use client";

import { useEffect, useState, type ReactNode } from "react";

import { DocsSearch } from "@/components/docs/docs-search";
import { DocumentationSidebar } from "@/components/docs/documentation-sidebar";
import { sectionById } from "@/components/docs/docs-sections";
import {
  MobileNavigation,
  MobileNavigationTrigger,
} from "@/components/docs/mobile-navigation";
import { PageContents, type PageContentsItem } from "@/components/docs/page-contents";
import { TopNavbar } from "@/components/docs/top-navbar";

const PRODUCT_LINKS = [
  { label: "Documentation", href: "/docs" },
  { label: "Guides", href: "/docs/guides" },
  { label: "Changelog", href: "/changelog" },
  // Help lives on the contact page rather than inside the docs tree.
  { label: "Help Center", href: "/contact" },
];

export interface DocsShellProps {
  /** Selects which sidebar groups render, and which page is marked current. */
  sectionId: "platform" | "developer";
  /** Which navbar item is highlighted. */
  activeNav?: string;
  activeGroup?: string;
  pageContents?: PageContentsItem[];
  children: ReactNode;
}

/**
 * Chrome shared by every documentation page: navbar, search, mobile drawer, sidebar
 * and the article column.
 *
 * Keeping this in one place is what stops the docked rail and the mobile drawer from
 * diverging, and it is what lets the Platform and Developer sections differ by data
 * rather than by markup.
 *
 * The ⌘K / Ctrl+K shortcut is bound here rather than in the palette so it works
 * wherever the reader happens to be on the page.
 */
export function DocsShell({
  sectionId,
  activeNav,
  activeGroup,
  pageContents,
  children,
}: DocsShellProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const section = sectionById(sectionId);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() !== "k" || !(event.metaKey || event.ctrlKey)) return;
      // Let a focused text field keep the keystroke.
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA") return;
      event.preventDefault();
      setSearchOpen(true);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const links = PRODUCT_LINKS.map((link) => ({
    ...link,
    active: link.label === activeNav,
  }));

  return (
    <div className="min-h-dvh bg-background">
      <TopNavbar
        productName="Pkay TDAI"
        links={links}
        menu={<MobileNavigationTrigger onClick={() => setDrawerOpen(true)} />}
        onOpenSearch={() => setSearchOpen(true)}
      />

      <DocsSearch open={searchOpen} onOpenChange={setSearchOpen} />

      <MobileNavigation
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        section={section}
        groups={section.groups}
        activeGroup={activeGroup}
      />

      {/*
        The rail is docked to the viewport edge rather than sitting inside a centred
        max-width container. Constraining the whole layout left an unbordered void to
        the left of the sidebar on any screen wider than that container, because the
        navbar's rule runs edge to edge while the sidebar's did not.
      */}
      <div className="flex w-full items-start">
        <aside className="sticky top-14 hidden h-[calc(100dvh-3.5rem)] w-[240px] shrink-0 border-r border-border bg-background lg:block">
          <DocumentationSidebar
            section={section}
            groups={section.groups}
            activeGroup={activeGroup}
          />
        </aside>

        <main className="min-w-0 flex-1 px-4 py-10 sm:px-8 lg:px-10 lg:py-14">
          {/* Stacks on small screens: the page-contents disclosure sits above the
              article and becomes a right-hand rail from `xl`. */}
          <div className="flex flex-col gap-10 xl:flex-row xl:gap-12">
            <article className="order-2 min-w-0 max-w-[820px] flex-1 xl:order-1">
              {children}
            </article>

            {pageContents ? (
              <PageContents
                items={pageContents}
                className="order-1 w-full shrink-0 xl:order-2 xl:w-[212px]"
              />
            ) : null}
          </div>
        </main>
      </div>
    </div>
  );
}