"use client";

import { usePathname } from "next/navigation";
import { cn } from "cn";

import { Navbar } from "@/components/navbar";
import { BotSupports } from "@/components/bot/bot-supports";

/**
 * Application shell: fixed top navigation, scrollable content and the global
 * floating Bot Supports launcher. Full-bleed routes (dashboard, AI chat) fill
 * the viewport so their content can size to the window (navbar stays fixed).
 */
/**
 * Routes that manage their own height.
 *
 * These fill the viewport and hide overflow, so a page can size its columns to the
 * window and pin a composer to the bottom edge. Everything else gets the centred,
 * padded, scrolling document layout.
 *
 * A chat surface missing from this list still looks plausible but does not fill: its
 * root asks for `h-full`, which resolves to `auto` against an auto-height parent, and
 * the parent's `px-4 pb-16 pt-20` then shows up as dead space at the top and bottom
 * with the sidebar inset from the window edge.
 */
const FULLSCREEN_ROUTES = ["/dashboard", "/ai", "/zenmux"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const fullscreen = FULLSCREEN_ROUTES.includes(pathname);

  return (
    <div className="min-h-dvh w-full">
      <Navbar />
      <main
        className={cn(
          fullscreen
            ? "h-dvh w-full overflow-hidden"
            : "mx-auto w-full max-w-[1600px] px-4 pb-16 pt-20 md:px-6",
        )}
      >
        {children}
      </main>
      <BotSupports />
    </div>
  );
}