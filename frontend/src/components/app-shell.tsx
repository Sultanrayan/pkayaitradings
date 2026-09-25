"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BarChart3,
  Bell,
  Bot,
  CandlestickChart,
  Home,
  LayoutDashboard,
  Newspaper,
  Radio,
  ShieldAlert,
  type LucideIcon,
} from "lucide-react";
import { cn } from "cn";

import { UserProfile } from "@/components/user-profile";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Home", icon: Home, exact: true },
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/charts", label: "Charts & Analysis", icon: CandlestickChart },
  { href: "/signals", label: "Signals Feed", icon: Radio },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/news", label: "News & Events", icon: Newspaper },
  { href: "/risk", label: "Risk Analysis", icon: ShieldAlert },
  { href: "/performance", label: "Performance", icon: BarChart3 },
  { href: "/alerts", label: "Alerts", icon: Bell },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const isActive = (item: NavItem) =>
    item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);

  return (
    <div className="flex min-h-dvh w-full">
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col border-r border-border bg-sidebar md:flex">
        <div className="flex items-center gap-3 border-b border-border px-4 py-4">
          <div className="relative size-9 shrink-0 overflow-hidden rounded-lg ring-1 ring-border">
            <Image
              src="/logo-pkay.jpg"
              alt="Pkay TDAI"
              fill
              sizes="36px"
              priority
              className="object-cover"
            />
          </div>
          <div>
            <div className="text-sm font-semibold tracking-tight">Pkay TDAI</div>
            <div className="text-[11px] text-muted-foreground">Multi-Agent Intelligence</div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = isActive(item);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                )}
              >
                <Icon className="size-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border p-3">
          <UserProfile variant="sidebar" />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 border-b border-border bg-background/85 backdrop-blur md:hidden">
          <div className="flex items-center justify-between gap-3 px-4 py-2.5">
            <div className="flex items-center gap-2">
              <div className="relative size-7 shrink-0 overflow-hidden rounded-md ring-1 ring-border">
                <Image src="/logo-pkay.jpg" alt="Pkay TDAI" fill sizes="28px" className="object-cover" />
              </div>
              <span className="text-sm font-semibold">Pkay TDAI</span>
            </div>
          </div>

          <nav className="flex gap-1 overflow-x-auto border-t border-border px-2 py-1.5">
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active = isActive(item);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1 text-xs",
                    active ? "bg-accent text-foreground" : "text-muted-foreground",
                  )}
                >
                  <Icon className="size-3.5" />
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </header>

        <main className="min-w-0 flex-1 px-4 py-6 md:px-6">{children}</main>

        <footer className="border-t border-border px-4 py-3 text-[11px] text-muted-foreground md:px-6">
          © 2026 Pkay TDAI. All rights reserved. Copying or reproducing any part of this user
          interface is prohibited.
        </footer>
      </div>
    </div>
  );
}
