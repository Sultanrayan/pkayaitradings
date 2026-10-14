"use client";

import Link from "next/link";
import Image from "next/image";
import { Search } from "lucide-react";

import { SearchBar } from "@/components/docs/search-bar";
import { cn } from "cn";

export interface TopNavLink {
  label: string;
  href: string;
  active?: boolean;
}

export interface TopNavbarProps {
  productName: string;
  productHref?: string;
  links: TopNavLink[];
  /** Rendered at the leading edge, before the product mark. Used for the menu button. */
  menu?: React.ReactNode;
  onOpenSearch?: () => void;
  className?: string;
}

/**
 * Sticky product bar for the documentation site.
 *
 * The search field is rendered on wide viewports and collapses to an icon button
 * below `lg`, which is what keeps it reachable on a phone without letting the bar
 * wrap. The horizontal inset here — `px-4 sm:px-6` — is the gutter the sidebar
 * matches, so the product mark and the section selector line up.
 */
export function TopNavbar({
  productName,
  productHref = "/",
  links,
  menu,
  onOpenSearch,
  className,
}: TopNavbarProps) {
  return (
    <header
      className={cn(
        "sticky top-0 z-50 w-full border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/80",
        className,
      )}
    >
      {/* Full width with no centred max-width, so the product mark sits at the same
          24px gutter as the sidebar content below it on every screen width. */}
      <div className="flex h-14 w-full items-center gap-3 px-4 sm:gap-4 sm:px-6">
        {menu}

        <Link
          href={productHref}
          className="flex shrink-0 items-center gap-2 rounded-md font-semibold tracking-tight focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <span className="relative size-7 shrink-0 overflow-hidden rounded-md ring-1 ring-border">
            <Image src="/logo-pkay.jpg" alt={productName} fill sizes="28px" className="object-cover" />
          </span>
          <span className="hidden text-sm sm:inline">{productName}</span>
        </Link>

        <nav aria-label="Product" className="hidden items-center md:flex">
          {links.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              aria-current={link.active ? "page" : undefined}
              className={cn(
                "relative rounded-md px-3 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                link.active
                  ? "font-medium text-foreground after:absolute after:inset-x-3 after:-bottom-[13px] after:h-px after:bg-foreground"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-2">
          <SearchBar className="hidden lg:flex" onClick={onOpenSearch} />

          <button
            type="button"
            onClick={onOpenSearch}
            aria-label="Search documentation"
            className="grid size-8 place-items-center rounded-md border border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring lg:hidden"
          >
            <Search className="size-4" />
          </button>
        </div>
      </div>
    </header>
  );
}