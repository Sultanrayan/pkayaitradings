"use client";

import { useSyncExternalStore } from "react";

/**
 * Hydration-safe clock.
 *
 * Seeding state with `Date.now()` renders different values on the server and
 * the client, which breaks hydration. This is a module-level external store
 * instead: the server snapshot is a fixed `0` and the real clock is only
 * adopted after React subscribes on the client, so the first client render
 * always matches the server HTML.
 *
 * Returns `0` until mounted — callers must treat that as "not yet known".
 */

const TICK_MS = 1_000;

let snapshot = 0;
let timer: ReturnType<typeof setInterval> | null = null;
const listeners = new Set<() => void>();

function handleTick() {
  snapshot = Date.now();
  for (const listener of listeners) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (timer === null) {
    snapshot = Date.now();
    listener();
    timer = setInterval(handleTick, TICK_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

const getSnapshot = () => snapshot;
const getServerSnapshot = () => 0;

/** Milliseconds since the epoch, or `0` before hydration completes. */
export function useNow(): number {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/** True once the real clock has been adopted (i.e. after hydration). */
export function useIsHydrated(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => snapshot > 0,
    () => false,
  );
}
