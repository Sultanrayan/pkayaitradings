"use client";

import { useEffect, useState } from "react";

/**
 * A ticking clock for time-based UI (countdowns, relative filters).
 *
 * The initial value is captured lazily so render stays pure; subsequent
 * updates come from an interval callback.
 */
export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);

  return now;
}
