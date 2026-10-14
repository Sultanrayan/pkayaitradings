"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Camera,
  Maximize2,
  MessageSquareText,
  Minimize2,
  RotateCcw,
  ZoomIn,
} from "lucide-react";

import { PriceChart, type ChartOverlays, type PriceChartHandle } from "@/components/charts/price-chart";
import { IndicatorChart } from "@/components/charts/indicator-chart";
import { PairSelector } from "@/components/trading/pair-selector";
import { TimeframeSelector } from "@/components/trading/timeframe-selector";
import {
  IndicatorsMenu,
  INDICATOR_ITEMS,
  type IndicatorKey,
} from "@/components/trading/indicators-menu";
import { useMarketContext } from "@/components/symbol-provider";
import { GenerateAnalysisDialog } from "@/components/dashboard/generate-analysis-dialog";
import { AiAnalysisPanel } from "@/components/dashboard/ai-analysis-panel";
import {
  IntelSection,
  MarketConditions,
  MarketSummary,
  MultiTimeframe,
  SignalHistory,
  TechnicalAnalysis,
} from "@/components/dashboard/intel-sections";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState, ErrorNote, LoadingRows } from "@/components/shared/primitives";
import { useOhlc } from "@/hooks/use-ohlc";
import { useSignals } from "@/hooks/use-api";
import { useDemoMarket, useDemoMode } from "@/hooks/use-demo-market";
import { useNow } from "@/hooks/use-now";
import {
  MTF_TIMEFRAMES,
  timeframeLabel,
  useTimeframeReads,
} from "@/hooks/use-timeframe-reads";
import { atr, bollinger, macd, rsi, stochastic } from "@/lib/indicators";
import { detectPreSignal, LEVEL_COLOR } from "@/lib/pre-signal";
import { cn } from "cn";
import { formatClock, formatQuoteAge } from "@/lib/format";
import { deriveMarketIntel, signalBias, type Bias } from "@/lib/market-intel";
import type { ChartTimeframe, ChartType } from "@/lib/types";

const CHART_TYPES: Array<{ key: ChartType; label: string; icon: string }> = [
  { key: "candlestick", label: "Candles", icon: "▮" },
  { key: "line", label: "Line", icon: "—" },
  { key: "area", label: "Area", icon: "◔" },
];

type HistoryFilter = "All" | "Bullish" | "Bearish";

/**
 * AI Market Analysis & Intelligence dashboard.
 *
 * Information flow: market summary → chart + AI analysis → conditions →
 * technical → multi-timeframe → AI summary + signal history.
 *
 * Read-only by design: everything here is an analytical insight. There is no
 * order execution, wallet or portfolio surface.
 */
export function DashboardView() {
  const router = useRouter();
  const { symbol, timeframe, setTimeframe, activeTick } = useMarketContext();
  const demo = useDemoMode();
  const demoMarket = useDemoMarket(demo, timeframe);
  const { series, loading, error } = useOhlc(symbol, timeframe, 400);
  const signals = useSignals({ symbol, limit: 60 });
  const [historyFilter, setHistoryFilter] = useState<HistoryFilter>("All");
  const now = useNow();
  const [signalDialogOpen, setSignalDialogOpen] = useState(false);
  const [signalDialogKey, setSignalDialogKey] = useState(0);
  const chartRef = useRef<PriceChartHandle | null>(null);
  const chartCardRef = useRef<HTMLDivElement | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [chartType, setChartType] = useState<ChartType>("candlestick");

  // No indicator panes by default – they are revealed via the Indicators menu.
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

  const bars = useMemo(
    () => (demo ? demoMarket?.series.bars ?? [] : series?.bars ?? []),
    [demo, demoMarket, series],
  );
  const closes = useMemo(() => bars.map((bar) => bar.close), [bars]);
  const effectiveSignals = useMemo(
    () => (demo ? demoMarket?.signals ?? [] : signals.data),
    [demo, demoMarket, signals.data],
  );
  // Only the market *state* comes from the live tick. The displayed quote is
  // derived from candles so it holds still between refreshes.
  const marketOpen = useMemo(() => {
    const tick = demo ? demoMarket?.tick : activeTick;
    return tick ? tick.marketState === "open" : null;
  }, [demo, demoMarket, activeTick]);

  /** Change across the visible candle window (not the streaming tick). */
  const windowChangePercent = useMemo(() => {
    if (bars.length < 2) return null;
    const first = bars[0].close;
    const last = bars[bars.length - 1].close;
    if (!first) return null;
    return ((last - first) / first) * 100;
  }, [bars]);

  const intel = useMemo(
    () => deriveMarketIntel(bars, effectiveSignals, effectiveSignals[0] ?? null),
    [bars, effectiveSignals],
  );

  const indicatorSeries = useMemo(() => {
    if (!bars.length) return null;
    const macdResult = macd(closes, 12, 26, 9);
    return {
      rsi: rsi(closes, 14),
      macd: macdResult,
      atr: atr(bars, 14),
      stochastic: stochastic(bars, 14, 3),
      bollinger: bollinger(closes, 20, 2),
    };
  }, [bars, closes]);

  // The AI does not draw on the graph: signal markers are intentionally absent.
  // Pre-signal zones are drawn automatically — no user toggle required.
  const preSignal = useMemo(() => detectPreSignal(bars, intel.structure), [bars, intel.structure]);
  const preSignalLines = useMemo(
    () =>
      preSignal.ready
        ? preSignal.zones.map((zone) => ({
            price: zone.price,
            label: zone.label,
            title: `${zone.label} ${zone.key === "be" ? "· VWAP" : "· Open"}`,
            color: LEVEL_COLOR[preSignal.level],
            lineStyle: (zone.key === "be" ? 0 : 2) as 0 | 2,
          }))
        : [],
    [preSignal],
  );

  // Support / resistance drawn from price structure only.
  //
  // The AI is not permitted to draw on the graph, so nothing here is derived
  // from a stored signal: levels come from recent swing extremes in the
  // candles the user is already looking at.
  const levels = useMemo(() => {
    if (!bars.length) return undefined;
    const window = bars.slice(-60);
    return {
      support: Math.min(...window.map((bar) => bar.low)),
      resistance: Math.max(...window.map((bar) => bar.high)),
    };
  }, [bars]);

  const demoBarsFor = useCallback(
    (target: ChartTimeframe) => (target === timeframe ? bars : []),
    [timeframe, bars],
  );
  const frameReads = useTimeframeReads(symbol, demo, demoBarsFor);

  const latestSignal = effectiveSignals[0] ?? null;
  const aiBias: Bias = latestSignal ? signalBias(latestSignal) : intel.structure;
  const signalConfidence = latestSignal
    ? Math.min(Math.max(latestSignal.confidence, 0), 1)
    : null;

  /**
   * The Decision Maker's own BUY/SELL call and its published levels.
   *
   * `effectiveSignals` is ordered latest-first, so the first directional
   * decision found is the most recent one. A newer WAIT cycle therefore does
   * not blank out a recommendation that is still live.
   */
  const tradeCall = useMemo(() => {
    const record = effectiveSignals.find((candidate) => {
      if (candidate.agent !== "decision_maker") return false;
      const value = candidate.direction.toUpperCase();
      return value === "BUY" || value === "SELL";
    });
    if (!record) return null;
    const payload = record.payload as {
      entry_price?: number | null;
      take_profit?: number | null;
      stop_loss?: number | null;
    };
    return {
      recommendation: record.direction.toUpperCase() as "BUY" | "SELL",
      entryPrice: payload.entry_price ?? null,
      takeProfit: payload.take_profit ?? null,
      stopLoss: payload.stop_loss ?? null,
    };
  }, [effectiveSignals]);
  const reasoning = useMemo(() => {
    const payload = latestSignal?.payload as { reasoning?: string } | undefined;
    return payload?.reasoning ?? null;
  }, [latestSignal]);

  const history = useMemo(
    () =>
      effectiveSignals.map((record) => ({
        id: record.id,
        bias: signalBias(record),
        confidence: Math.min(Math.max(record.confidence, 0), 1),
        time: formatClock(record.created_at),
      })),
    [effectiveSignals],
  );

  const toggleFullscreen = useCallback(async () => {
    const element = chartCardRef.current;
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

  const openSignalDialog = () => {
    setSignalDialogKey((value) => value + 1);
    setSignalDialogOpen(true);
  };

  const indicatorsOn = INDICATOR_ITEMS.some((indicator) => indicators[indicator.key]);
  const displaySymbol = `${symbol.slice(0, 3)}/${symbol.slice(3)}`;
  const chartLoading = !demo && loading && bars.length === 0;

  return (
    <div className="h-full overflow-y-auto pt-14">
      <div className="mx-auto w-full max-w-[1600px] space-y-3 px-3 py-3 md:px-4">
        {/* 1 — Market control bar */}
        <div className="-mx-3 flex items-center gap-2 overflow-x-auto px-3 md:mx-0 md:px-0">
          <PairSelector assets={demo ? demoMarket?.symbols : undefined} />
          <TimeframeSelector />
          <IndicatorsMenu
            overlays={overlays}
            indicators={indicators}
            onToggleOverlay={toggleOverlay}
            onToggleIndicator={toggleIndicator}
          />
          <div className="ml-auto flex items-center gap-1.5">
            <Button size="sm" onClick={openSignalDialog}>
              Generate Signal
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={() => router.push("/ai")}
            >
              <MessageSquareText className="size-3.5" />
              Ask AI
            </Button>
          </div>
        </div>

        {error ? <ErrorNote>{error}</ErrorNote> : null}

        {/* 2 — Market summary: PRICE · AI SIGNAL · MARKET STRUCTURE */}
        <MarketSummary
          displaySymbol={displaySymbol}
          // Deliberately candle-derived, not the streaming tick: the quote and
          // change stay put until the page is refreshed or the timeframe
          // changes, so a waiting chart never looks like it is drifting.
          price={intel.price}
          changePercent={windowChangePercent}
          marketOpen={marketOpen}
          intel={intel}
          signalConfidence={signalConfidence}
          signalBias={aiBias}
          recommendation={tradeCall?.recommendation ?? null}
          entryPrice={tradeCall?.entryPrice ?? null}
          takeProfit={tradeCall?.takeProfit ?? null}
          stopLoss={tradeCall?.stopLoss ?? null}
          signalAge={
            latestSignal && now > 0
              ? formatQuoteAge((now - new Date(latestSignal.created_at).getTime()) / 1000)
              : null
          }
        />

        {/* 3 — Chart (70%) + AI analysis (30%) */}
        <div className="grid gap-3 xl:grid-cols-10">
          <Card ref={chartCardRef} className="bg-card/40 ring-border xl:col-span-7">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
              <span className="text-sm font-medium tracking-wide">
                {displaySymbol} · {timeframeLabel(timeframe)}
              </span>
              <div className="flex items-center gap-1">
                <div className="flex items-center overflow-hidden rounded-md border border-border">
                  {CHART_TYPES.map((type) => (
                    <button
                      key={type.key}
                      type="button"
                      onClick={() => setChartType(type.key)}
                      title={type.label}
                      aria-label={type.label}
                      aria-pressed={chartType === type.key}
                      className={cn(
                        "h-7 px-2 text-xs transition-colors",
                        chartType === type.key
                          ? "bg-accent text-foreground"
                          : "text-muted-foreground hover:bg-accent/50",
                      )}
                    >
                      {type.icon}
                    </button>
                  ))}
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  title="Fit content"
                  aria-label="Fit content"
                  onClick={() => chartRef.current?.fitContent()}
                >
                  <ZoomIn className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  title="Reset view"
                  aria-label="Reset view"
                  onClick={() => {
                    setChartType("candlestick");
                    chartRef.current?.fitContent();
                  }}
                >
                  <RotateCcw className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  title="Screenshot (PNG)"
                  aria-label="Screenshot (PNG)"
                  onClick={() => chartRef.current?.screenshot()}
                >
                  <Camera className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  title={fullscreen ? "Exit fullscreen" : "Fullscreen"}
                  aria-label="Toggle fullscreen"
                  onClick={() => void toggleFullscreen()}
                >
                  {fullscreen ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
                </Button>
              </div>
            </div>
            <CardContent className="p-3">
              {chartLoading ? (
                <LoadingRows rows={6} />
              ) : bars.length === 0 ? (
                <EmptyState>No candle data available for {symbol}.</EmptyState>
              ) : (
                <div className="flex flex-col">
                  <PriceChart
                    ref={chartRef}
                    bars={bars}
                    overlays={overlays}
                    levels={levels}
                    preSignal={preSignalLines}
                    height={420}
                    chartType={chartType}
                  />
                  {indicatorsOn && indicatorSeries ? (
                    <div className="mt-3 max-h-[300px] space-y-3 overflow-y-auto border-t border-border pt-3">
                      {indicators.rsi ? (
                        <IndicatorChart
                          title="RSI (14)"
                          bars={bars}
                          references={[30, 70]}
                          lines={[{ label: "RSI", color: "#eab308", values: indicatorSeries.rsi }]}
                        />
                      ) : null}
                      {indicators.macd ? (
                        <IndicatorChart
                          title="MACD (12,26,9)"
                          bars={bars}
                          references={[0]}
                          histogram={indicatorSeries.macd.histogram}
                          lines={[
                            { label: "MACD", color: "#3b82f6", values: indicatorSeries.macd.macd },
                            { label: "Signal", color: "#f97316", values: indicatorSeries.macd.signal },
                          ]}
                        />
                      ) : null}
                      {indicators.atr ? (
                        <IndicatorChart
                          title="ATR (14)"
                          bars={bars}
                          lines={[{ label: "ATR", color: "#a855f7", values: indicatorSeries.atr }]}
                        />
                      ) : null}
                      {indicators.stochastic ? (
                        <IndicatorChart
                          title="Stochastic (14,3)"
                          bars={bars}
                          references={[20, 80]}
                          lines={[
                            { label: "%K", color: "#3b82f6", values: indicatorSeries.stochastic.k },
                            { label: "%D", color: "#f97316", values: indicatorSeries.stochastic.d },
                          ]}
                        />
                      ) : null}
                    </div>
                  ) : null}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="xl:col-span-3">
            <AiAnalysisPanel
              intel={intel}
              signalBias={aiBias}
              signalConfidence={signalConfidence}
              loading={chartLoading}
              reasoning={reasoning}
            />
          </div>
        </div>

        {/* 4 — Market conditions */}
        <MarketConditions intel={intel} />

        {/* 5 — Technical analysis */}
        <TechnicalAnalysis rows={intel.technical} />

        {/* 6 — Multi-timeframe */}
        <MultiTimeframe
          frames={MTF_TIMEFRAMES.map((frame) => ({
            value: frame,
            label: timeframeLabel(frame),
            bias: frameReads[frame]?.bias ?? "Neutral",
            score: frameReads[frame]?.score ?? 0.5,
          }))}
          active={timeframe}
          onSelect={(value) => setTimeframe(value as ChartTimeframe)}
        />

        {/* 7 — AI summary + signal history */}
        <div className="grid gap-3 lg:grid-cols-5">
          <IntelSection
            title="AI summary"
            hint={`${displaySymbol} · ${timeframeLabel(timeframe)}`}
            className="lg:col-span-3"
          >
            <p className="text-sm leading-relaxed">
              {intel.ready ? (
                <>
                  <span className="font-medium">{displaySymbol}</span> is showing{" "}
                  <span
                    className={cn(
                      "font-medium",
                      intel.structure === "Bullish"
                        ? "text-bull"
                        : intel.structure === "Bearish"
                          ? "text-bear"
                          : "text-flat",
                    )}
                  >
                    {intel.structure.toLowerCase()}
                  </span>{" "}
                  structure on the {timeframeLabel(timeframe)} timeframe.{" "}
                  {intel.reasons[0] ?? "Indicators are still loading."}
                </>
              ) : (
                "The summary appears once candles have loaded."
              )}
            </p>
            {reasoning ? (
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {reasoning}
              </p>
            ) : null}
          </IntelSection>

          <div className="lg:col-span-2">
            <SignalHistory
              entries={history}
              filter={historyFilter}
              onFilterChange={setHistoryFilter}
            />
          </div>
        </div>
      </div>

      <GenerateAnalysisDialog
        key={signalDialogKey}
        open={signalDialogOpen}
        onOpenChange={setSignalDialogOpen}
        onGenerated={() => signals.reload()}
      />

      </div>
  );
}
