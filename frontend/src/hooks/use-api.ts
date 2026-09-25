"use client";

import { useCallback, useEffect, useRef } from "react";

import { useAsyncData } from "@/hooks/use-async-data";
import { api } from "@/lib/api";
import type {
  AgentStatus,
  Alert,
  CalendarEvent,
  CalendarFilters,
  MarketMover,
  NewsArticle,
  PerformanceStats,
  SignalFilters,
  SignalRecord,
} from "@/lib/types";

export function useSignals(filters: SignalFilters = {}) {
  const filtersRef = useRef(filters);
  useEffect(() => {
    filtersRef.current = filters;
  });
  const key = JSON.stringify(filters);
  const loader = useCallback(() => api.signals(filtersRef.current), []);
  return useAsyncData<SignalRecord[]>(`signals:${key}`, loader, []);
}

export function useAgents() {
  const loader = useCallback(() => api.agents(), []);
  return useAsyncData<AgentStatus[]>("agents", loader, []);
}

export function usePerformance() {
  const loader = useCallback(() => api.performance(), []);
  return useAsyncData<PerformanceStats | null>("performance", loader, null);
}

export function useAlerts(limit = 50) {
  const loader = useCallback(() => api.alerts(limit), [limit]);
  return useAsyncData<Alert[]>(`alerts:${limit}`, loader, []);
}

export function useNews(symbol?: string, limit = 15) {
  const loader = useCallback(() => api.news(symbol, limit), [symbol, limit]);
  return useAsyncData<NewsArticle[]>(`news:${symbol ?? "all"}:${limit}`, loader, []);
}

export function useCalendar(filters: CalendarFilters = {}) {
  const filtersRef = useRef(filters);
  useEffect(() => {
    filtersRef.current = filters;
  });
  const key = JSON.stringify(filters);
  const loader = useCallback(() => api.calendar(filtersRef.current), []);
  return useAsyncData<CalendarEvent[]>(`calendar:${key}`, loader, []);
}

export function useMarketMovers(kind: "gainers" | "losers" | "most-active" = "gainers") {
  const loader = useCallback(() => api.marketMovers(kind, 10), [kind]);
  return useAsyncData<MarketMover[]>(`movers:${kind}`, loader, []);
}
