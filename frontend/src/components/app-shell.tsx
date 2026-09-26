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
export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const fullscreen = pathname === "/dashboard" || pathname === "/ai";

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