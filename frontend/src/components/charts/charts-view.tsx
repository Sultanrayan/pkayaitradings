"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { Camera, Maximize2, Minimize2, SlidersHorizontal } from "lucide-react";
import { cn } from "cn";

import { IndicatorChart } from "@/components/charts/indicator-chart";
import { PriceChart, type ChartOverlays, type PriceChartHandle } from "@/components/charts/price-chart";
import { useMarketContext } from "@/components/symbol-provider";
import { EmptyState, ErrorNote, LoadingRows, PageHeader, Panel } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import { useOhlc } from "@/hooks/use-ohlc";
import { atr, bollinger, ema, macd, rsi, stochastic } from "@/lib/indicators";
import { CHART_TIMEFRAMES } from "@/lib/constants";
import { formatPrice } from "@/lib/format";
import type { Timeframe } from "@/lib/types";

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

/**
 * Signal markers are intentionally not drawn: the AI is not authorised to
 * write onto the graph. Anything rendered here derives from market data only.
 */

export function ChartsView() {
  const { symbol, timeframe, setTimeframe, symbols, setSymbol, ticks } = useMarketContext();
  const { series, loading, error } = useOhlc(symbol, timeframe, 400);
  const chartRef = useRef<PriceChartHandle | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [fullscreen, setFullscreen] = useState(false);

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

  // Levels come from price structure only — never from an AI signal payload.
  const levels = useMemo(() => {
    if (!bars.length) return undefined;
    const window = bars.slice(-60);
    return {
      support: Math.min(...window.map((bar) => bar.low)),
      resistance: Math.max(...window.map((bar) => bar.high)),
    };
  }, [bars]);

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
    <div className="space-y-6">
      <PageHeader
        title="Charts & Analysis"
        description={`${symbol} · ${timeframe} — candlesticks with overlays, indicator panes and price levels.`}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => chartRef.current?.fitContent()} className="gap-1.5">
              <SlidersHorizontal className="size-3.5" />
              Fit
            </Button>
            <Button variant="outline" size="sm" onClick={() => chartRef.current?.screenshot()} className="gap-1.5">
              <Camera className="size-3.5" />
              PNG
            </Button>
            <Button variant="outline" size="sm" onClick={() => void toggleFullscreen()} className="gap-1.5">
              {fullscreen ? <Minimize2 className="size-3.5" /> : <Maximize2 className="size-3.5" />}
              Fullscreen
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 rounded-lg border border-border p-0.5">
          {symbols.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setSymbol(item)}
              className={cn(
                "rounded-md px-3 py-1 text-xs font-medium transition-colors",
                item === symbol ? "bg-foreground text-background" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 rounded-lg border border-border p-0.5">
          {CHART_TIMEFRAMES.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setTimeframe(item as Timeframe)}
              className={cn(
                "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                item === timeframe ? "bg-accent text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {item}
            </button>
          ))}
        </div>
        <div className="tabular ml-auto text-sm text-muted-foreground">
          Last <span className="text-foreground">{ticks[symbol]?.mid.toFixed(2) ?? "—"}</span>
        </div>
      </div>

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      <div
        ref={containerRef}
        className="space-y-4 rounded-xl bg-card p-3 ring-1 ring-border"
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-border pb-3">
          <span className="text-[11px] uppercase tracking-wider text-muted-foreground">Overlays</span>
          {OVERLAY_LABELS.map((overlay) => (
            <button
              key={overlay.key}
              type="button"
              onClick={() => toggleOverlay(overlay.key)}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                overlays[overlay.key]
                  ? "border-border bg-accent text-foreground"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              <span className="size-2 rounded-full" style={{ background: overlay.color }} />
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
                "rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                indicators[indicator.key]
                  ? "border-border bg-accent text-foreground"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              {indicator.label}
            </button>
          ))}
        </div>

        {loading && bars.length === 0 ? (
          <LoadingRows rows={8} />
        ) : bars.length === 0 ? (
          <EmptyState>No candles available for {symbol} {timeframe}.</EmptyState>
        ) : (
          <>
            <PriceChart ref={chartRef} bars={bars} overlays={overlays} levels={levels} height={440} />

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

      <Panel title="Price levels" description="Drawn from recent swing extremes in the candle data">
        <div className="flex flex-wrap gap-4 text-xs">
          <span className="text-bear">
            Resistance {levels?.resistance ? formatPrice(levels.resistance) : "—"}
          </span>
          <span className="text-muted-foreground">
            Support {levels?.support ? formatPrice(levels.support) : "—"}
          </span>
          <span className="text-muted-foreground">
            Over the last {Math.min(bars.length, 60)} candles
          </span>
        </div>
      </Panel>
    </div>
  );
}
