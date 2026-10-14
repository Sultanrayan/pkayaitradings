/**
 * Static content and small helpers for the Zenmux surface.
 *
 * Kept apart from the view so the copy can be asserted in tests without rendering
 * anything, and so the model list has exactly one definition in the client.
 */

import type { ZenmuxModelId, ZenmuxModelOption, ZenmuxTimeframe } from "@/lib/api";

/**
 * The two selectable models, deepest first.
 *
 * Mirrors the server registry in `orchestrator/zenmux.py`. The server remains the
 * source of truth — `/api/v1/zenmux/models` returns the same two — but the UI
 * renders these immediately so the selector never flashes empty on load.
 */
export const ZENMUX_MODELS: ZenmuxModelOption[] = [
  { id: "super", name: "Super Zenmux", description: "Deep market analysis" },
  { id: "flash", name: "Flash Zenmux", description: "Fast market analysis" },
];

/** Deep analysis by default: the more thorough of the two. */
export const DEFAULT_ZENMUX_MODEL: ZenmuxModelId = "super";

/** The only instrument this screen covers. */
export const ZENMUX_SYMBOL_LABEL = "XAU/USD";

/**
 * Timeframes the analysis can be read on.
 *
 * M5 and M15 only, and that ceiling is a data limit rather than a design choice:
 * the market feed returns about three days of M5, which clears the 55-bar minimum
 * a 50-period average needs at M15 (96 bars) but nowhere near it at H1 (24 bars).
 *
 * The classifier still scores M5 whatever is picked here, so a higher timeframe
 * changes the structure read and the levels, not the probability. The card labels
 * which is which.
 */
export const ZENMUX_TIMEFRAMES: ZenmuxTimeframe[] = ["M5", "M15"];

export const DEFAULT_ZENMUX_TIMEFRAME: ZenmuxTimeframe = "M5";

/**
 * Phrases offered in the composer's phrase box.
 *
 * These are the screen's prompt library. With no text field, they are the only way to
 * discover what can be asked, and each one doubles as the staged text the composer
 * reveals and then sends.
 *
 * Tapping a phrase stages it whole; selecting a single word inside one first stages
 * just that word. The phrases are therefore written as complete sentences that still
 * make sense narrowed down — "trend", "key support and resistance levels" — rather
 * than as fragments that only work in full.
 *
 * This is the only prompt list. The four one-click quick actions that used to sit
 * above the composer were removed rather than kept alongside it: two overlapping
 * lists of things to ask, in the same small area, is clutter that makes both harder
 * to scan.
 *
 * Deliberately no instrument name in the wording. XAU/USD is fixed for this screen
 * and shown in the footer, so naming it in every phrase just adds length.
 */
export const SPEAKABLE_PHRASES: string[] = [
  "What's the trend on gold right now?",
  "Where are the key support and resistance levels?",
  "Is gold overbought or oversold?",
  "Give me a market summary.",
  "How volatile is gold today?",
  "What's the current price action?",
  "What do the higher timeframes show?",
  "How far is gold from its recent high?",
  "Break down the gold chart for me.",
];

/**
 * Resting text in the composer.
 *
 * Says nothing about voice: the composer stages a phrase and waits for Enter, so a
 * hint about speaking would describe a control that is not there.
 */
export const COMPOSER_HINT = "Ask about XAU/USD.";

export type ConversationGroup = "Today" | "Yesterday" | "Previous 7 days";

/**
 * Bucket a timestamp into a sidebar group.
 *
 * Boundaries are calendar-based, not rolling-24-hour: a conversation from 23:50
 * yesterday belongs with yesterday's work, which is what someone scanning the
 * sidebar expects. Anything older than seven days returns null and is not shown,
 * because an unbounded list under a "Previous 7 days" heading would mislabel its
 * own contents.
 *
 * @param createdAt - Epoch milliseconds.
 * @param now - Injectable for tests; defaults to the current time.
 */
export function groupFor(createdAt: number, now: number = Date.now()): ConversationGroup | null {
  const startOfToday = new Date(now);
  startOfToday.setHours(0, 0, 0, 0);
  const todayStart = startOfToday.getTime();

  const day = 24 * 60 * 60 * 1000;
  if (createdAt >= todayStart) return "Today";
  if (createdAt >= todayStart - day) return "Yesterday";
  if (createdAt >= todayStart - 7 * day) return "Previous 7 days";
  return null;
}

/** Sequence the groups are listed in, newest first. */
export const GROUP_ORDER: ConversationGroup[] = ["Today", "Yesterday", "Previous 7 days"];

/**
 * Derive a short conversation title from its first user turn.
 *
 * Strips the XAU/USD boilerplate so a list of chats started from quick actions
 * does not read as eight copies of the same sentence, and keeps the result under
 * one line at sidebar width.
 */
export function titleFrom(text: string): string {
  const cleaned = text
    .replace(/\bxau\/?usd\b/gi, "gold")
    .replace(/\s+/g, " ")
    .trim();
  const base = cleaned || "New chat";
  return base.length > 34 ? `${base.slice(0, 34).trimEnd()}…` : base;
}
