"use client";

import { useCallback, useSyncExternalStore } from "react";

const STORAGE_KEY = "pkay.watchlist";

let current: string[] = [];
let hydrated = false;
const listeners = new Set<() => void>();

function read(): string[] {
  return current;
}

function notify(): void {
  for (const listener of listeners) listener();
}

function persist(): void {
  notify();
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
  } catch {
    /* storage unavailable */
  }
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function hydrate(): void {
  if (hydrated || typeof window === "undefined") return;
  hydrated = true;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as unknown;
      if (Array.isArray(parsed)) {
        current = parsed.filter((item): item is string => typeof item === "string");
      }
    }
  } catch {
    current = [];
  }
}

function toggleSymbol(symbol: string): void {
  hydrate();
  const normalized = symbol.toUpperCase();
  current = current.includes(normalized)
    ? current.filter((item) => item !== normalized)
    : [...current, normalized];
  persist();
}

function isWatched(symbol: string): boolean {
  hydrate();
  return current.some((item) => item === symbol.toUpperCase());
}

/**
 * Watchlist/favourites backed by localStorage, exposed through
 * `useSyncExternalStore` so all open panels stay in sync.
 */
export function useWatchlist(): {
  symbols: string[];
  toggle: (symbol: string) => void;
  contains: (symbol: string) => boolean;
} {
  hydrate();
  const symbols = useSyncExternalStore(subscribe, read, read);
  const toggle = useCallback((symbol: string) => toggleSymbol(symbol), []);
  const contains = useCallback((symbol: string) => isWatched(symbol), []);
  return { symbols, toggle, contains };
}