"use client";

import { useSyncExternalStore } from "react";

export interface CommunityBotContext {
  /** Short label describing what the user is looking at. */
  label: string;
  /** Post / chart / market / discussion text provided to the AI. */
  detail: string;
  symbol?: string;
}

let current: CommunityBotContext | null = null;
const listeners = new Set<() => void>();

function getSnapshot(): CommunityBotContext | null {
  return current;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Set the Community context the Bot Supports panel should understand. */
export function setCommunityBotContext(context: CommunityBotContext | null): void {
  current = context;
  for (const listener of listeners) listener();
}

/** Subscribe to the active Community bot context (read by BotSupports). */
export function useCommunityBotContext(): CommunityBotContext | null {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}