"use client";

import { Navbar } from "@/components/navbar";
import { BotSupports } from "@/components/bot/bot-supports";

/**
 * Application shell: fixed top navigation, scrollable content and the global
 * floating Bot Supports launcher.
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh w-full">
      <Navbar />
      <main className="mx-auto w-full max-w-[1600px] px-4 pb-16 pt-20 md:px-6">{children}</main>
      <BotSupports />
    </div>
  );
}