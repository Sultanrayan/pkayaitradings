"use client";

/**
 * User-scoped browser storage.
 *
 * Several features keep per-user state in `localStorage` (profile, watchlist,
 * preferences, AI chat history, community drafts, alert rules). Without any
 * scoping, signing in as a different account on the same browser exposes the
 * previous user's data — a real cross-account leak.
 *
 * These keys are therefore wiped whenever the session ends or the signed-in
 * identity changes. Layout-only keys (widget positions) are intentionally left
 * alone: they carry no user data.
 */

const USER_SCOPED_KEYS = [
  "pkay.profile",
  "pkay.watchlist",
  "pkay.preferences",
  "pkay.analysis-request",
  "pkay.signal-request",
  "pkay.ai.chats",
  "pkay.social",
  "pkay.alerts.rules",
] as const;

/** Keys that survive an account switch because they hold no user data. */
const SHARED_KEYS = new Set([
  "pkay.admin.widgets",
  "pkay.presignal.widgets",
]);

/**
 * Remove every locally stored record that belongs to the user who just left.
 * Safe to call when nothing is stored.
 */
export function clearUserScopedStorage(): void {
  if (typeof window === "undefined") return;
  try {
    for (const key of USER_SCOPED_KEYS) {
      window.localStorage.removeItem(key);
    }
    // Catch any per-user key added later without updating the list above.
    const stale: string[] = [];
    for (let index = 0; index < window.localStorage.length; index += 1) {
      const key = window.localStorage.key(index);
      if (key && key.startsWith("pkay.") && !SHARED_KEYS.has(key)) stale.push(key);
    }
    for (const key of stale) window.localStorage.removeItem(key);
  } catch {
    /* storage is best-effort */
  }
}
