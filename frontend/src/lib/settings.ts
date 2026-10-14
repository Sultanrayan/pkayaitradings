/**
 * User preferences store.
 *
 * Extends the existing local-storage implementation (same `pkay.preferences`
 * key the settings page already used) into a small external store so the
 * settings page, the settings dialog and other views can all read the same
 * values without prop drilling or duplicate storage systems.
 *
 * Swapping in a backend settings API later only requires replacing
 * `getSettings` / `saveSettings`.
 */

import type { ChartType, ChartTimeframe } from "@/lib/types";

export const ANALYSIS_TYPES = [
  "Comprehensive Analysis",
  "Technical Analysis",
  "Market Structure",
  "Momentum",
  "Sentiment",
  "Volume",
] as const;

export const AI_FOCUS_OPTIONS = [
  { key: "technical", label: "Technical" },
  { key: "structure", label: "Structure" },
  { key: "momentum", label: "Momentum" },
  { key: "sentiment", label: "Sentiment" },
  { key: "volume", label: "Volume" },
  { key: "news", label: "News" },
] as const;

export const THEME_OPTIONS = [
  { value: "dark", label: "Dark" },
  { value: "light", label: "Light" },
  { value: "system", label: "System" },
] as const;

export const DENSITY_OPTIONS = [
  { value: "compact", label: "Compact" },
  { value: "comfortable", label: "Comfortable" },
  { value: "spacious", label: "Spacious" },
] as const;

export const EXPLANATION_STYLES = [
  { value: "concise", label: "Concise" },
  { value: "balanced", label: "Balanced" },
  { value: "detailed", label: "Detailed" },
] as const;

export const ANALYSIS_DETAILS = [
  { value: "quick", label: "Quick" },
  { value: "standard", label: "Standard" },
  { value: "deep", label: "Deep" },
] as const;

export const CHART_TYPES: Array<{ value: ChartType; label: string }> = [
  { value: "candlestick", label: "Candlestick" },
  { value: "line", label: "Line" },
  { value: "area", label: "Area" },
];

export interface Settings {
  // AI analysis preferences
  defaultSymbol: string;
  defaultTimeframe: ChartTimeframe;
  defaultAnalysisType: string;
  /** 0..1 — lower-confidence analysis is de-emphasised in the feed. */
  minConfidence: number;

  // AI display
  showExplanations: boolean;
  showConfidenceBreakdown: boolean;
  showIndicators: boolean;
  showLevels: boolean;
  showMultiTimeframe: boolean;
  showReasoning: boolean;

  // Chart preferences
  chartType: ChartType;
  chartVolume: boolean;
  chartEma: boolean;
  chartRsi: boolean;
  chartMacd: boolean;
  chartLevels: boolean;
  chartAutoRefresh: boolean;

  // Notification settings
  notifyAnalysis: boolean;
  notifyHighConfidence: boolean;
  notifyTrendChange: boolean;
  notifyMarketEvent: boolean;
  notifyNewsSentiment: boolean;
  notifyDailySummary: boolean;
  notifyWeeklyReport: boolean;

  // Notification channels
  channelEmail: boolean;
  channelTelegram: boolean;
  channelPush: boolean;
  channelInApp: boolean;

  // Do not disturb
  dndEnabled: boolean;
  dndStart: string;
  dndEnd: string;

  // Appearance
  theme: string;
  density: string;
  animations: boolean;
  language: string;

  // Privacy & data
  saveHistory: boolean;
  personalizeAi: boolean;
  saveSearches: boolean;
  anonymousAnalytics: boolean;

  // AI preferences
  explanationStyle: string;
  analysisDetail: string;
  aiFocus: string[];
}

export const DEFAULT_SETTINGS: Settings = {
  defaultSymbol: "XAUUSD",
  defaultTimeframe: "H1",
  defaultAnalysisType: "Comprehensive Analysis",
  minConfidence: 0.65,

  showExplanations: true,
  showConfidenceBreakdown: true,
  showIndicators: true,
  showLevels: true,
  showMultiTimeframe: true,
  showReasoning: true,

  chartType: "candlestick",
  chartVolume: true,
  chartEma: true,
  chartRsi: false,
  chartMacd: false,
  chartLevels: true,
  chartAutoRefresh: true,

  notifyAnalysis: true,
  notifyHighConfidence: true,
  notifyTrendChange: true,
  notifyMarketEvent: true,
  notifyNewsSentiment: false,
  notifyDailySummary: true,
  notifyWeeklyReport: false,

  channelEmail: false,
  channelTelegram: false,
  channelPush: true,
  channelInApp: true,

  dndEnabled: false,
  dndStart: "22:00",
  dndEnd: "07:00",

  theme: "dark",
  density: "comfortable",
  animations: true,
  language: "en",

  saveHistory: true,
  personalizeAi: true,
  saveSearches: true,
  anonymousAnalytics: true,

  explanationStyle: "balanced",
  analysisDetail: "standard",
  aiFocus: AI_FOCUS_OPTIONS.map((option) => option.key),
};

export const STORAGE_KEY = "pkay.preferences";

let current: Settings = DEFAULT_SETTINGS;
let hydrated = false;
const listeners = new Set<() => void>();

function hydrate(): void {
  if (hydrated || typeof window === "undefined") return;
  hydrated = true;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      current = { ...DEFAULT_SETTINGS, ...(JSON.parse(raw) as Partial<Settings>) };
    }
  } catch {
    /* ignore malformed storage */
  }
}

export function getSettings(): Settings {
  hydrate();
  return current;
}

export function saveSettings(next: Settings): void {
  current = { ...next };
  hydrated = true;
  if (typeof window !== "undefined") {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(current));
    } catch {
      /* storage is best-effort */
    }
  }
  for (const listener of listeners) listener();
}

/** Apply a partial update without the caller rebuilding the whole object. */
export function patchSettings(patch: Partial<Settings>): void {
  saveSettings({ ...getSettings(), ...patch });
}

export function resetSettings(): void {
  saveSettings(DEFAULT_SETTINGS);
}

export function subscribeSettings(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Remove every locally stored preference. Used by "Clear local data". */
export function clearLocalSettings(): void {
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* storage is best-effort */
    }
  }
  current = DEFAULT_SETTINGS;
  for (const listener of listeners) listener();
}
