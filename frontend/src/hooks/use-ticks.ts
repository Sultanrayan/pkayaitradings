"use client";

import { useEffect, useRef, useState } from "react";

import { authToken, WS_BASE_URL } from "@/lib/api";
import type { Tick, TickFrame } from "@/lib/types";

export type StreamStatus = "connecting" | "live" | "reconnecting" | "error";

export interface TickStream {
  ticks: Record<string, Tick>;
  status: StreamStatus;
  lastUpdate: number | null;
}

/**
 * Subscribe to live ticks over the backend WebSocket.
 *
 * The server sends a `snapshot` frame immediately after connecting, then a
 * `tick` frame per update. Reconnects with exponential backoff.
 */
export function useTicks(symbols: string[]): TickStream {
  const [ticks, setTicks] = useState<Record<string, Tick>>({});
  const [status, setStatus] = useState<StreamStatus>("connecting");
  const [lastUpdate, setLastUpdate] = useState<number | null>(null);
  const symbolsKey = symbols.join(",");
  const attemptRef = useRef(0);

  useEffect(() => {
    if (!symbolsKey) return;
    let socket: WebSocket | null = null;
    let disposed = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      setStatus(attemptRef.current === 0 ? "connecting" : "reconnecting");
      const token = authToken();
      const query = `symbols=${encodeURIComponent(symbolsKey)}${token ? `&token=${encodeURIComponent(token)}` : ""}`;
      socket = new WebSocket(`${WS_BASE_URL}/ws/ticks?${query}`);

      socket.onopen = () => {
        attemptRef.current = 0;
        setStatus("live");
      };

      socket.onmessage = (event: MessageEvent<string>) => {
        let frame: TickFrame;
        try {
          frame = JSON.parse(event.data) as TickFrame;
        } catch {
          return;
        }
        if (frame.type === "snapshot") {
          setTicks(frame.ticks);
          setLastUpdate(Date.now());
        } else if (frame.type === "tick") {
          setTicks((previous) => ({ ...previous, [frame.tick.symbol]: frame.tick }));
          setLastUpdate(Date.now());
        } else if (frame.type === "error") {
          setStatus("error");
        }
      };

      socket.onerror = () => setStatus("error");

      socket.onclose = () => {
        if (disposed) return;
        attemptRef.current += 1;
        setStatus("reconnecting");
        const delay = Math.min(1000 * 2 ** attemptRef.current, 15000);
        retryTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      disposed = true;
      if (retryTimer) clearTimeout(retryTimer);
      socket?.close();
    };
  }, [symbolsKey]);

  return { ticks, status, lastUpdate };
}
