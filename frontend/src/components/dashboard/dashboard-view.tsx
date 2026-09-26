"use client";

import Image from "next/image";
import { useCallback, useMemo, useRef, useState } from "react";
import { Camera, Maximize2, Minimize2, ZoomIn } from "lucide-react";

import btcImg from "../../../img/btc.png";
import goldImg from "../../../img/gold.png";

import { PriceChart, type ChartMarker, type ChartOverlays, type PriceChartHandle } from "@/components/charts/price-chart";
import { IndicatorChart } from "@/components/charts/indicator-chart";
import { PairSelector } from "@/components/trading/pair-selector";
import { TimeframeSelector } from "@/components/trading/timeframe-selector";
import {
  IndicatorsMenu,
  INDICATOR_ITEMS,
  type IndicatorKey,
} from "@/components/trading/indicators-menu";
import { useMarketContext } from "@/components/symbol-provider";
import { Button } from "@/components/ui/button";
import { ErrorNote, EmptyState, LoadingRows } from "@/components/shared/primitives";
import { useOhlc } from "@/hooks/use-ohlc";
import { useSignals } from "@/hooks/use-api";
import { useDemoMarket, useDemoMode } from "@/hooks/use-demo-market";
import { useWatchlist } from "@/hooks/use-watchlist";
import { atr, bollinger, ema, macd, rsi, stochastic } from "@/lib/indicators";
import { cn } from "cn";
import { formatPrice, formatSignedPercent } from "@/lib/format";
import type { StaticImageData } from "next/image";
import type { ChartType, OhlcBar, SignalRecord } from "@/lib/types";

const CHART_TYPES: Array<{ key: ChartType; label: string; icon: string }> = [
  { key: "candlestick", label: "Candles", icon: "▮" },
  { key: "line", label: "Line", icon: "—" },
  { key: "area", label: "Area", icon: "◔" },
];

/** Demo symbol image (from frontend/img) used as the price badge. */
function symbolBadge(symbol: string): StaticImageData {
  if (symbol.toUpperCase().startsWith("XAU")) return goldImg;
  if (symbol.toUpperCase().startsWith("BTC")) return btcImg;
  return goldImg;
}

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

/**
 * Fullscreen TradingView-style dashboard. The chart fills the viewport beneath
 * the fixed navbar; the pair and timeframe selectors are dropdown-only, and
 * extra chart chrome is tucked behind the settings menu.
 */
export function DashboardView() {
  const { symbol, timeframe, activeTick } = useMarketContext();
  const demo = useDemoMode();
  const demoMarket = useDemoMarket(demo, timeframe);
  const { series, loading, error } = useOhlc(symbol, timeframe, 400);
  const signals = useSignals({ symbol, agent: "technical_analyst", limit: 60 });
  const { contains, toggle } = useWatchlist();
  const chartRef = useRef<PriceChartHandle | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [chartType, setChartType] = useState<ChartType>("candlestick");

  // No indicators on by default – they are revealed via the Indicators dropdown.
  const [overlays, setOverlays] = useState<ChartOverlays>({
    ema20: true,
    ema50: true,
    ema200: false,
    bollinger: false,
    volume: true,
  });
  const [indicators, setIndicators] = useState<Record<IndicatorKey, boolean>>({
    rsi: false,
    macd: false,
    atr: false,
    stochastic: false,
  });

  const bars = useMemo(() => (demo ? demoMarket?.series.bars ?? [] : series?.bars ?? []), [demo, demoMarket, series]);
  const closes = useMemo(() => bars.map((bar) => bar.close), [bars]);
  const effectiveSignals = useMemo(
    () => (demo ? demoMarket?.signals ?? [] : signals.data),
    [demo, demoMarket, signals.data],
  );
  const effectiveTick = useMemo(() => (demo ? demoMarket?.tick : activeTick), [demo, demoMarket, activeTick]);

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

  const markers = useMemo(() => signalsToMarkers(bars, effectiveSignals), [bars, effectiveSignals]);

  const latestTechnical = effectiveSignals.find((record) => record.kind === "technical_signal");
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

  const watched = contains(symbol);
  const change = effectiveTick?.dayDiffPercent ?? null;
  const changeTone = change === null ? "text-muted-foreground" : change >= 0 ? "text-bull" : "text-bear";

  const indicatorsOn = INDICATOR_ITEMS.some((indicator) => indicators[indicator.key]);

  return (
    <div className="flex h-full flex-col pt-14 pb-3">
      {/* App bar: price, chart actions */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-card px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          {demo ? (
            <Image
              src={symbolBadge(symbol)}
              alt={symbol}
              width={24}
              height={24}
              className="size-6 rounded-full object-cover"
              priority
            />
          ) : null}
          <span className="tabular text-sm font-semibold">{formatPrice(effectiveTick?.mid)}</span>
          <span className={cn("tabular text-xs font-medium", changeTone)}>{formatSignedPercent(change)}</span>
          <button
            type="button"
            aria-label={watched ? "Remove from watchlist" : "Add to watchlist"}
            onClick={() => toggle(symbol)}
            className={cn(
              "rounded p-1 outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring",
              watched ? "text-gold" : "text-muted-foreground",
            )}
          >
            <svg viewBox="0 0 24 24" fill={watched ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" className="size-4">
              <path d="M11.5 4.5l2.1 4.3 4.7.7-3.4 3.3.8 4.7-4.2-2.2-4.2 2.2.8-4.7-3.4-3.3 4.7-.7z" />
            </svg>
          </button>
        </div>

        <div className="ml-auto flex items-center gap-1.5">
          <div className="flex items-center overflow-hidden rounded-md border border-border">
            {CHART_TYPES.map((type) => (
              <button
                key={type.key}
                type="button"
                onClick={() => setChartType(type.key)}
                title={type.label}
                aria-label={type.label}
                className={cn(
                  "h-8 px-2 text-xs transition-colors",
                  chartType === type.key ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50",
                )}
              >
                {type.icon}
              </button>
            ))}
          </div>
          <Button variant="ghost" size="icon" title="Fit content" aria-label="Fit content" onClick={() => chartRef.current?.fitContent()}>
            <ZoomIn className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" title="Screenshot (PNG)" aria-label="Screenshot (PNG)" onClick={() => chartRef.current?.screenshot()}>
            <Camera className="size-4" />
          </Button>
          <Button variant="ghost" size="icon" title={fullscreen ? "Exit fullscreen" : "Fullscreen"} aria-label="Toggle fullscreen" onClick={() => void toggleFullscreen()}>
            {fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
          </Button>
        </div>
      </div>

      {/* Chart toolbar: pair, timeframe, indicators dropdowns */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-muted/20 px-3 py-1.5">
        <PairSelector assets={demo ? demoMarket?.symbols : undefined} />
        <TimeframeSelector />
        <IndicatorsMenu
          overlays={overlays}
          indicators={indicators}
          onToggleOverlay={toggleOverlay}
          onToggleIndicator={toggleIndicator}
        />
        {indicatorsOn ? (
          <span className="ml-auto text-[11px] uppercase tracking-wider text-muted-foreground">
            Indicator panes shown — use the menu to hide
          </span>
        ) : null}
      </div>

      {!demo && error ? (
        <div className="px-3 py-2">
          <ErrorNote>{error}</ErrorNote>
        </div>
      ) : null}

      {/* Chart fills the remaining screen height */}
      <div ref={containerRef} className="relative min-h-0 flex-1">
        {!demo && loading && bars.length === 0 ? (
          <div className="h-full">
            <LoadingRows rows={6} className="h-full" />
          </div>
        ) : bars.length === 0 ? (
          <div className="flex h-full items-center justify-center p-4">
            <EmptyState>No candle data available for {symbol}.</EmptyState>
          </div>
        ) : (
          <div className="flex h-full flex-col">
            <div className="min-h-0 flex-1">
              <PriceChart
                ref={chartRef}
                bars={bars}
                overlays={overlays}
                levels={levels}
                markers={markers}
                height="auto"
                chartType={chartType}
              />
            </div>

            {indicatorsOn ? (
              <div className="max-h-[40%] w-full shrink-0 overflow-y-auto border-t border-border">
                {computed && indicators.rsi ? (
                  <IndicatorChart title="RSI (14)" bars={bars} references={[30, 70]} lines={[{ label: "RSI", color: "#eab308", values: computed.rsi }]} />
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
                  <IndicatorChart title="ATR (14)" bars={bars} lines={[{ label: "ATR", color: "#a855f7", values: computed.atr }]} />
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
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}