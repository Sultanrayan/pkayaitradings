"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { Camera, Maximize2, Minimize2, SlidersHorizontal } from "lucide-react";
import { cn } from "cn";

import { PriceChart, type ChartMarker, type ChartOverlays, type PriceChartHandle } from "@/components/charts/price-chart";
import { IndicatorChart } from "@/components/charts/indicator-chart";
import { AssetHeader } from "@/components/trading/asset-header";
import { AssetPicker } from "@/components/trading/asset-picker";
import { TimeframeSelector } from "@/components/trading/timeframe-selector";
import { useMarketContext } from "@/components/symbol-provider";
import { Button } from "@/components/ui/button";
import { EmptyState, ErrorNote, LoadingRows } from "@/components/shared/primitives";
import { useOhlc } from "@/hooks/use-ohlc";
import { useSignals } from "@/hooks/use-api";
import { atr, bollinger, ema, macd, rsi, stochastic } from "@/lib/indicators";
import type { ChartType, OhlcBar, SignalRecord } from "@/lib/types";

const CHART_TYPES: Array<{ key: ChartType; label: string }> = [
  { key: "candlestick", label: "Candles" },
  { key: "line", label: "Line" },
  { key: "area", label: "Area" },
];

const OVERLAY_LABELS: Array<{ key: keyof ChartOverlays; label: string; color: string }> = [
  { key: "ema20", label: "EMA 20", color: "#eab308" },
  { key: "ema50", label: "EMA 50", color: "#3b82f6" },
  { key: "ema200", label: "EMA 200", color: "#a855f7" },
  { key: "bollinger", label: "Bollinger", color: "#52525b" },
  { key: "volume", label: "Volume", color: "#71717a" },
];

const INDICATOR_LABELS = [
  { key: "rsi", label: "RSI" },
  { key: "macd", label: "MACD" },
  { key: "atr", label: "ATR" },
  { key: "stochastic", label: "Stochastic" },
] as const;

type IndicatorKey = (typeof INDICATOR_LABELS)[number]["key"];

function snapToBar(bars: OhlcBar[], iso: string): number | null {
  if (!bars.length) return null;
  const target = new Date(iso).getTime();
  let best: number | null = null;
  for (const bar of bars) {
    const time = new Date(bar.openTime).getTime();
    if (time <= target) best = time;
    else break;
  }
  return best ?? new Date(bars[0].openTime).getTime();
}

function signalsToMarkers(bars: OhlcBar[], signals: SignalRecord[]): ChartMarker[] {
  const markers: ChartMarker[] = [];
  for (const signal of signals) {
    if (signal.kind !== "technical_signal") continue;
    const snapped = snapToBar(bars, signal.created_at);
    if (snapped === null) continue;
    if (signal.direction === "BULLISH") {
      markers.push({
        time: Math.floor(snapped / 1000),
        position: "belowBar",
        color: "#22c55e",
        shape: "arrowUp",
        text: "BUY",
      });
    } else if (signal.direction === "BEARISH") {
      markers.push({
        time: Math.floor(snapped / 1000),
        position: "aboveBar",
        color: "#ef4444",
        shape: "arrowDown",
        text: "SELL",
      });
    }
  }
  return markers;
}

export function DashboardView() {
  const { symbol, timeframe } = useMarketContext();
  const { series, loading, error } = useOhlc(symbol, timeframe, 400);
  const signals = useSignals({ symbol, agent: "technical_analyst", limit: 60 });
  const chartRef = useRef<PriceChartHandle | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [chartType, setChartType] = useState<ChartType>("candlestick");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const [overlays, setOverlays] = useState<ChartOverlays>({
    ema20: true,
    ema50: true,
    ema200: false,
    bollinger: false,
    volume: true,
  });
  const [indicators, setIndicators] = useState<Record<IndicatorKey, boolean>>({
    rsi: true,
    macd: true,
    atr: false,
    stochastic: false,
  });

  const bars = useMemo(() => series?.bars ?? [], [series]);
  const closes = useMemo(() => bars.map((bar) => bar.close), [bars]);

  const computed = useMemo(() => {
    if (!bars.length) return null;
    const macdResult = macd(closes, 12, 26, 9);
    return {
      rsi: rsi(closes, 14),
      macd: macdResult,
      atr: atr(bars, 14),
      stochastic: stochastic(bars, 14, 3),
      bollinger: bollinger(closes, 20, 2),
      ema20: ema(closes, 20),
      ema50: ema(closes, 50),
      ema200: ema(closes, 200),
    };
  }, [bars, closes]);

  const markers = useMemo(() => signalsToMarkers(bars, signals.data), [bars, signals.data]);

  const latestTechnical = signals.data.find((record) => record.kind === "technical_signal");
  const levels = useMemo(() => {
    const payload = latestTechnical?.payload as
      | { key_levels?: { support?: number | null; resistance?: number | null } }
      | undefined;
    return payload?.key_levels ?? undefined;
  }, [latestTechnical]);

  const toggleFullscreen = useCallback(async () => {
    const element = containerRef.current;
    if (!element) return;
    if (document.fullscreenElement) {
      await document.exitFullscreen();
      setFullscreen(false);
    } else {
      await element.requestFullscreen();
      setFullscreen(true);
    }
  }, []);

  const toggleOverlay = (key: keyof ChartOverlays) =>
    setOverlays((previous) => ({ ...previous, [key]: !previous[key] }));
  const toggleIndicator = (key: IndicatorKey) =>
    setIndicators((previous) => ({ ...previous, [key]: !previous[key] }));

  return (
    <div className="space-y-4">
      <AssetHeader />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <TimeframeSelector />
        <div className="flex items-center gap-1.5">
          <div className="flex items-center gap-0.5 rounded-lg border border-border bg-card p-0.5">
            {CHART_TYPES.map((type) => (
              <button
                key={type.key}
                type="button"
                onClick={() => setChartType(type.key)}
                className={cn(
                  "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                  chartType === type.key
                    ? "bg-accent text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {type.label}
              </button>
            ))}
          </div>

          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => chartRef.current?.fitContent()}>
            <SlidersHorizontal className="size-3.5" />
            Fit
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => chartRef.current?.screenshot()}>
            <Camera className="size-3.5" />
            PNG
          </Button>
          <Button variant="outline" size="sm" className="gap-1.5" onClick={() => void toggleFullscreen()}>
            {fullscreen ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
            {fullscreen ? "Exit" : "Full"}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div
          ref={containerRef}
          className={cn(
            "space-y-4 rounded-xl bg-card p-3 ring-1 ring-border",
            fullscreen && "fixed inset-0 z-[60] overflow-auto rounded-none p-4",
          )}
        >
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border pb-3 text-xs">
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">Overlays</span>
            {OVERLAY_LABELS.map((overlay) => (
              <button
                key={overlay.key}
                type="button"
                onClick={() => toggleOverlay(overlay.key)}
                className={cn(
                  "flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                  overlays[overlay.key]
                    ? "border-border bg-accent text-foreground"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                <span className="size-1.5 rounded-full" style={{ background: overlay.color }} />
                {overlay.label}
              </button>
            ))}
            <span className="ml-2 text-[11px] uppercase tracking-wider text-muted-foreground">Panes</span>
            {INDICATOR_LABELS.map((indicator) => (
              <button
                key={indicator.key}
                type="button"
                onClick={() => toggleIndicator(indicator.key)}
                className={cn(
                  "rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                  indicators[indicator.key]
                    ? "border-border bg-accent text-foreground"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {indicator.label}
              </button>
            ))}
            <button
              type="button"
              onClick={() => setSettingsOpen((value) => !value)}
              className="ml-auto rounded-full border border-border px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
            >
              {settingsOpen ? "Hide settings" : "Chart settings"}
            </button>
          </div>

          {settingsOpen ? (
            <div className="rounded-lg border border-border p-3 text-sm">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1.5">
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Type</div>
                  <div className="flex gap-1">
                    {CHART_TYPES.map((type) => (
                      <button
                        key={type.key}
                        type="button"
                        onClick={() => setChartType(type.key)}
                        className={cn(
                          "rounded-md border px-2 py-1 text-xs",
                          chartType === type.key ? "border-foreground bg-accent text-foreground" : "border-border text-muted-foreground",
                        )}
                      >
                        {type.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="space-y-1.5">
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Data</div>
                  <div className="text-xs text-muted-foreground">
                    {bars.length} candles · {timeframe} · {symbol}
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {error ? <ErrorNote>{error}</ErrorNote> : null}

          {loading && bars.length === 0 ? (
            <LoadingRows rows={6} />
          ) : bars.length === 0 ? (
            <EmptyState>No candle data available for {symbol}.</EmptyState>
          ) : (
            <>
              <PriceChart
                ref={chartRef}
                bars={bars}
                overlays={overlays}
                levels={levels}
                markers={markers}
                height={fullscreen ? 620 : 440}
                chartType={chartType}
              />

              {computed && indicators.rsi ? (
                <IndicatorChart
                  title="RSI (14)"
                  bars={bars}
                  references={[30, 70]}
                  lines={[{ label: "RSI", color: "#eab308", values: computed.rsi }]}
                />
              ) : null}

              {computed && indicators.macd ? (
                <IndicatorChart
                  title="MACD (12,26,9)"
                  bars={bars}
                  references={[0]}
                  histogram={computed.macd.histogram}
                  lines={[
                    { label: "MACD", color: "#3b82f6", values: computed.macd.macd },
                    { label: "Signal", color: "#f97316", values: computed.macd.signal },
                  ]}
                />
              ) : null}

              {computed && indicators.atr ? (
                <IndicatorChart
                  title="ATR (14)"
                  bars={bars}
                  lines={[{ label: "ATR", color: "#a855f7", values: computed.atr }]}
                />
              ) : null}

              {computed && indicators.stochastic ? (
                <IndicatorChart
                  title="Stochastic (14,3)"
                  bars={bars}
                  references={[20, 80]}
                  lines={[
                    { label: "%K", color: "#3b82f6", values: computed.stochastic.k },
                    { label: "%D", color: "#f97316", values: computed.stochastic.d },
                  ]}
                />
              ) : null}
            </>
          )}
        </div>

        <aside className="hidden lg:block">
          <div className="sticky top-[4.5rem] rounded-xl bg-card p-3 ring-1 ring-border">
            <div className="mb-3 px-1 text-[11px] uppercase tracking-wider text-muted-foreground">
              Assets
            </div>
            <AssetPicker />
          </div>
        </aside>
      </div>

      <div className="lg:hidden">
        <AssetPicker />
      </div>
    </div>
  );
}