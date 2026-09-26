"use client";

import { useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { Menu, X } from "lucide-react";
import { cn } from "cn";

import { Logo } from "@/components/navbar/logo";
import { NotificationsMenu } from "@/components/navbar/notifications-menu";
import { ProfileMenu } from "@/components/navbar/profile-menu";
import { Button } from "@/components/ui/button";

const NAV_LINKS = [
  { href: "/community", label: "Community" },
  { href: "/signals", label: "Signal" },
  { href: "/news", label: "News" },
  { href: "/market", label: "Market" },
];

export function Navbar() {
  // Key by pathname so the mobile menu closes when navigating between routes.
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [menuKey, setMenuKey] = useState(pathname);

  // Close the drawer on navigation without a state-updating effect:
  // each route change mounts under a fresh key, resetting the local state.
  if (menuKey !== pathname) {
    setMenuKey(pathname);
    setMobileOpen(false);
  }

  return (
    <header className="fixed inset-x-0 top-0 z-50 border-b border-border bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
      <div className="flex h-14 items-center gap-3 px-4 md:gap-6 md:px-6">
        <Button
          variant="ghost"
          size="icon-sm"
          className="md:hidden"
          aria-label="Toggle navigation"
          onClick={() => setMobileOpen((open) => !open)}
        >
          {mobileOpen ? <X className="size-4" /> : <Menu className="size-4" />}
        </Button>

        <Logo />

        <nav className="ml-2 hidden items-center gap-1 md:flex">
          {NAV_LINKS.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                  active && "bg-accent text-foreground",
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-1.5">
          <NotificationsMenu />
          <ProfileMenu />
        </div>
      </div>

      {mobileOpen ? (
        <nav className="border-t border-border px-4 py-2 md:hidden">
          {NAV_LINKS.map((link) => {
            const active = pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "flex items-center rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                  active && "bg-accent text-foreground",
                )}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
      ) : null}
    </header>
  );
}