/**
 * Local user profile.
 *
 * There is no authentication backend yet, so the profile is a small
 * `localStorage`-backed store exposed to React via `useSyncExternalStore`.
 * Swapping in real auth later only requires changing `saveProfile`/`getProfile`.
 */

export interface Profile {
  name: string;
  email: string;
  role: string;
  avatarUrl?: string;
}

export const DEFAULT_PROFILE: Profile = {
  name: "Pkay Trader",
  email: "trader@pkay.ai",
  role: "Analyst",
};

const STORAGE_KEY = "pkay.profile";

let current: Profile = DEFAULT_PROFILE;
let hydrated = false;
const listeners = new Set<() => void>();

function hydrate(): void {
  if (hydrated || typeof window === "undefined") return;
  hydrated = true;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      current = { ...DEFAULT_PROFILE, ...(JSON.parse(raw) as Partial<Profile>) };
    }
  } catch {
    /* ignore malformed storage */
  }
}

/** Return the current profile, hydrating from storage on first access. */
export function getProfile(): Profile {
  hydrate();
  return current;
}

/** Persist a new profile and notify subscribers. */
export function saveProfile(next: Profile): void {
  current = next;
  hydrated = true;
  if (typeof window !== "undefined") {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  }
  for (const listener of listeners) listener();
}

/** Reset the profile to its default (used by "sign out"). */
export function resetProfile(): void {
  saveProfile(DEFAULT_PROFILE);
}

/** Subscribe to profile changes (for `useSyncExternalStore`). */
export function subscribeProfile(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Derive initials from a display name. */
export function profileInitials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean).slice(0, 2);
  const initials = parts.map((part) => part[0]?.toUpperCase() ?? "").join("");
  return initials || "PK";
}
