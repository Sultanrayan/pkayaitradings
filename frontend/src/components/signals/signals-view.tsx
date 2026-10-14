"use client";

import { useCallback, useMemo, useState } from "react";
import { Download, FileJson, LayoutGrid, List, RotateCcw } from "lucide-react";
import { cn } from "cn";

import { useMarketContext } from "@/components/symbol-provider";
import { IntelSection, SectionLabel } from "@/components/dashboard/intel-sections";
import { AnalysisCard, AnalysisRow } from "@/components/signals/analysis-card";
import { AnalysisDetail } from "@/components/signals/analysis-detail";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState, ErrorNote, LoadingRows } from "@/components/shared/primitives";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { useDemoMarket, useDemoMode } from "@/hooks/use-demo-market";
import { useNow } from "@/hooks/use-now";
import { useSignals } from "@/hooks/use-api";
import { useSymbolIntel } from "@/hooks/use-symbol-intel";
import { generateDemoSignalCards } from "@/lib/demo-data";
import {
  AGENT_FILTERS,
  ANALYSIS_TYPES,
  SIGNAL_TIMEFRAMES,
  biasToneOf,
  latestRecommendation,
  recommendationTone,
  toAnalysisInsight,
  weightedBias,
  type AgentLabel,
  type AnalysisInsight,
  type AnalysisType,
  type Recommendation,
} from "@/lib/analysis-model";
import { decimalsForPrice, formatDateTime, formatPrice } from "@/lib/format";
import { getSettings } from "@/lib/settings";
import type { ChartTimeframe, SignalRecord } from "@/lib/types";

type SortKey = "latest" | "confidence" | "symbol";
type ViewMode = "grid" | "list";

const CONSENSUS_SLOTS: Array<{ label: string; type: AnalysisType }> = [
  { label: "Technical analysis", type: "Technical" },
  { label: "News", type: "News" },
  { label: "Market structure", type: "Market Structure" },
  { label: "Sentiment", type: "Sentiment" },
];

function download(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function toCsv(insights: AnalysisInsight[]): string {
  const header = [
    "symbol",
    "timeframe",
    "analysis_type",
    "agent",
    "bias",
    "confidence",
    "summary",
    "timestamp",
  ];
  const rows = insights.map((insight) =>
    [
      insight.symbol,
      insight.timeframe ?? "",
      insight.analysisType,
      insight.agent,
      insight.bias,
      insight.confidence.toFixed(4),
      `"${(insight.summary ?? "").replace(/"/g, "'")}"`,
      insight.timestamp,
    ].join(","),
  );
  return [header.join(","), ...rows].join("\n");
}

function biasText(bias: AnalysisInsight["bias"]): string {
  if (bias === "Bullish") return "text-bull";
  if (bias === "Bearish") return "text-bear";
  return "text-flat";
}

function recText(recommendation: Recommendation): string {
  if (recommendation === "BUY") return "text-bull";
  if (recommendation === "SELL") return "text-bear";
  return "text-flat";
}

/** One entry / take-profit / stop figure from the backend trade decision. */
function SignalLevel({
  label,
  value,
  className,
}: {
  label: string;
  value: number | null;
  className?: string;
}) {
  return (
    <div className="rounded border border-border px-1.5 py-1">
      <div className="text-[9px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "tabular text-[11px] font-medium",
          value === null ? "text-muted-foreground/50" : className ?? "text-foreground",
        )}
      >
        {value === null ? "—" : formatPrice(value)}
      </div>
    </div>
  );
}

/**
 * AI Market Analysis feed.
 *
 * Read-only analytical surface: market bias, confidence, reasoning and key
 * levels. Filtering, sorting and the detail view all happen in place — no
 * navigation and no execution controls.
 */
export function SignalsView() {
  const { symbols, timeframe } = useMarketContext();
  const demo = useDemoMode();
  const now = useNow();

  const [symbol, setSymbol] = useState<string>("all");
  const [frame, setFrame] = useState<string>(timeframe);  const [analysisType, setAnalysisType] = useState<AnalysisType>("All");
  const [agent, setAgent] = useState<AgentLabel>("All");
  const [minConfidence, setMinConfidence] = useState(() =>
    Math.round(getSettings().minConfidence * 100),
  );
  const [sort, setSort] = useState<SortKey>("latest");
  const [view, setView] = useState<ViewMode>("grid");
  const [selected, setSelected] = useState<AnalysisInsight | null>(null);

  const signals = useSignals({ symbol: symbol === "all" ? undefined : symbol, limit: 200 });

  const demoSignals = useMemo(
    () => (demo ? generateDemoSignalCards(symbols.length ? symbols : undefined, 6, now) : []),
    [demo, symbols, now],
  );
  const records = useMemo(
    () => (demo ? demoSignals : signals.data),
    [demo, demoSignals, signals.data],
  );

  const insights = useMemo(
    () => records.map((record) => toAnalysisInsight(record, timeframe)),
    [records, timeframe],
  );

  const visibleSymbols = useMemo(
    () => [...new Set(insights.map((insight) => insight.symbol))],
    [insights],
  );

  const signalsFor = useCallback(
    (target: string) => records.filter((record: SignalRecord) => record.symbol === target),
    [records],
  );

  // Demo candles come from the market context so cards still show real bars.
  const demoMarket = useDemoMarket(demo, timeframe);
  const demoBarsFor = useCallback(
    (target: ChartTimeframe) =>
      target === timeframe ? demoMarket?.series.bars ?? [] : [],
    [timeframe, demoMarket],
  );

  const symbolReads = useSymbolIntel(
    visibleSymbols,
    timeframe,
    demo,
    demoBarsFor,
    signalsFor,
  );

  const filtered = useMemo(() => {
    const result = insights.filter((insight) => {
      if (symbol !== "all" && insight.symbol !== symbol) return false;
      if (frame !== "all" && insight.timeframe !== frame) return false;
      if (analysisType !== "All" && insight.analysisType !== analysisType) return false;
      if (agent !== "All" && insight.agent !== agent) return false;
      if (insight.confidence < minConfidence / 100) return false;
      return true;
    });

    return result.sort((a, b) => {
      if (sort === "confidence") return b.confidence - a.confidence;
      if (sort === "symbol") return a.symbol.localeCompare(b.symbol) || b.confidence - a.confidence;
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
    });
  }, [insights, symbol, frame, analysisType, agent, minConfidence, sort]);

  /** Most recent insight per analysis type — the latest analysis cycle. */
  const consensus = useMemo(() => {
    const latest = new Map<AnalysisType, AnalysisInsight>();
    for (const insight of insights) {
      const current = latest.get(insight.analysisType);
      if (!current || new Date(insight.timestamp) > new Date(current.timestamp)) {
        latest.set(insight.analysisType, insight);
      }
    }
    return CONSENSUS_SLOTS.map((slot) => ({
      ...slot,
      insight: latest.get(slot.type) ?? null,
    }));
  }, [insights]);

  const overall = useMemo(() => {
    const present = consensus
      .map((slot) => slot.insight)
      .filter((insight): insight is AnalysisInsight => insight !== null);
    return weightedBias(present);
  }, [consensus]);

  /** The active trade signal and the insight that produced it. */
  const activeCall = useMemo(() => latestRecommendation(insights), [insights]);

  const consensusBreakdown = useMemo(() => {
    const find = (type: AnalysisType) =>
      consensus.find((slot) => slot.type === type)?.insight?.confidence ?? null;
    const technical = find("Technical");
    const news = find("News");
    const structure = find("Market Structure");
    const momentum = symbolReads[visibleSymbols[0] ?? ""]?.intel;
    return [
      { label: "Technical", value: technical },
      { label: "Momentum", value: momentum ? momentum.score : null },
      { label: "News", value: news },
      { label: "Structure", value: structure },
    ];
  }, [consensus, symbolReads, visibleSymbols]);

  const resetFilters = () => {
    setSymbol("all");
    setFrame(timeframe);
    setAnalysisType("All");
    setAgent("All");
    setMinConfidence(0);
  };

  const exportCsv = () =>
    download("ai-analysis.csv", toCsv(filtered), "text/csv");
  const exportJson = () =>
    download("ai-analysis.json", JSON.stringify(filtered, null, 2), "application/json");

  const loading = !demo && signals.loading && records.length === 0;
  const symbolOptions = symbols.length ? symbols : visibleSymbols;

  return (
    <div className="space-y-3">
      {/* 1 — Page header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">AI Market Analysis</h1>
          <p className="mt-0.5 text-xs text-muted-foreground">
            AI-generated market insights from multiple analysis agents.
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="gap-1.5">
              <Download className="size-3.5" />
              Export
              <span className="text-muted-foreground">▾</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={exportCsv} className="gap-2">
              <Download className="size-3.5" />
              Export CSV
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={exportJson} className="gap-2">
              <FileJson className="size-3.5" />
              Export JSON
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* 2 — Filters */}
      <IntelSection
        title="Filters"
        hint={`${filtered.length} of ${insights.length} insights`}
        action={
          <button
            type="button"
            onClick={resetFilters}
            className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <RotateCcw className="size-3" />
            Reset filters
          </button>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <SectionLabel>Symbol</SectionLabel>
            <Select value={symbol} onValueChange={setSymbol}>
              <SelectTrigger size="sm" className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All symbols</SelectItem>
                {symbolOptions.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <SectionLabel>Timeframe</SectionLabel>
            <Select value={frame} onValueChange={setFrame}>
              <SelectTrigger size="sm" className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All timeframes</SelectItem>
                {SIGNAL_TIMEFRAMES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <SectionLabel>Analysis type</SectionLabel>
            <Select
              value={analysisType}
              onValueChange={(value) => setAnalysisType(value as AnalysisType)}
            >
              <SelectTrigger size="sm" className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ANALYSIS_TYPES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <SectionLabel>Agent</SectionLabel>
            <Select value={agent} onValueChange={(value) => setAgent(value as AgentLabel)}>
              <SelectTrigger size="sm" className="h-8">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AGENT_FILTERS.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5 sm:col-span-2 lg:col-span-4">
            <div className="flex items-center justify-between">
              <SectionLabel>Confidence</SectionLabel>
              <span className="tabular text-[11px] text-muted-foreground">
                {minConfidence}%+
              </span>
            </div>
            <Slider
              value={[minConfidence]}
              max={100}
              step={5}
              onValueChange={(value) => setMinConfidence(value[0] ?? 0)}
            />
          </div>
        </div>
      </IntelSection>

      {/* 3 + 4 — AI consensus with the explicit trade signal */}
      <IntelSection
        title="AI consensus"
        hint="Latest analysis cycle"
        action={
          <div className="text-right">
            <div className={cn("text-base font-semibold leading-none", recText(activeCall.recommendation))}>
              {activeCall.recommendation}
            </div>
            <div className="tabular mt-0.5 text-[10px] text-muted-foreground">
              {Math.round(overall.confidence * 100)}% confidence · trade signal
            </div>
          </div>
        }
      >
        <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {consensus.map((slot) => {
              const insight = slot.insight;
              const tone = insight
                ? insight.recommendation
                  ? recommendationTone(insight.recommendation)
                  : biasToneOf(insight.bias)
                : "flat";
              const pct = insight ? Math.round(insight.confidence * 100) : 0;
              return (
                <div key={slot.type} className="space-y-1.5">
                  <SectionLabel>{slot.label}</SectionLabel>
                  {insight ? (
                    <>
                      <div
                        className={cn(
                          "text-sm font-semibold",
                          insight.recommendation
                            ? recText(insight.recommendation)
                            : biasText(insight.bias),
                        )}
                      >
                        {insight.recommendation ?? insight.bias.toUpperCase()}
                      </div>
                      <div className="h-1 overflow-hidden rounded-full bg-muted">
                        <div
                          className={cn(
                            "h-full rounded-full",
                            tone === "bull" ? "bg-bull" : tone === "bear" ? "bg-bear" : "bg-flat",
                          )}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <div className="tabular text-[10px] text-muted-foreground">{pct}%</div>
                    </>
                  ) : (
                    <div className="space-y-1.5">
                      <div className="text-sm text-muted-foreground/60">—</div>
                      <div className="h-1 overflow-hidden rounded-full bg-muted">
                        <div className="h-full w-0" />
                      </div>
                      <div className="text-[10px] text-muted-foreground/60">pending</div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="space-y-2 border-t border-border pt-3 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
            <SectionLabel>Trade signal</SectionLabel>
            <div className={cn("text-xl font-semibold", recText(activeCall.recommendation))}>
              {activeCall.recommendation}
            </div>
            <div className="tabular text-[11px] text-muted-foreground">
              {activeCall.insight
                ? `${activeCall.insight.symbol} · ${activeCall.insight.timeframe ?? "current"} · ${formatDateTime(activeCall.insight.timestamp)}`
                : "no decision recorded yet"}
            </div>

            {/* Levels come straight from the backend TradeDecision; they are
                omitted for a WAIT because no position is being recommended. */}
            {activeCall.recommendation !== "WAIT" && activeCall.insight ? (
              <div className="grid grid-cols-3 gap-1 pt-1.5">
                <SignalLevel label="Entry" value={activeCall.insight.entryPrice} />
                <SignalLevel
                  label="Take profit"
                  value={activeCall.insight.takeProfit}
                  className="text-bull"
                />
                <SignalLevel
                  label="Stop loss"
                  value={activeCall.insight.stopLoss}
                  className="text-bear"
                />
              </div>
            ) : null}

            <div className="flex items-center justify-between border-t border-border pt-2 text-[11px]">
              <span className="text-muted-foreground">Overall market bias</span>
              <span className={cn("font-medium", biasText(overall.bias))}>
                {overall.bias.toUpperCase()}
              </span>
            </div>
            <div className="space-y-1.5 pt-1">
              {consensusBreakdown.map((part) => (
                <div key={part.label} className="space-y-1">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-muted-foreground">{part.label}</span>
                    <span className="tabular text-muted-foreground">
                      {part.value === null ? "pending" : `${Math.round(part.value * 100)}%`}
                    </span>
                  </div>
                  <div className="h-1 overflow-hidden rounded-full bg-muted">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        part.value === null
                          ? "bg-muted-foreground/30"
                          : part.value >= 0.55
                            ? "bg-bull"
                            : part.value <= 0.45
                              ? "bg-bear"
                              : "bg-foreground",
                      )}
                      style={{ width: `${part.value === null ? 0 : Math.round(part.value * 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </IntelSection>

      {/* 5 — Analysis feed */}
      <IntelSection
        title="Analysis feed"
        hint="Latest AI insights across markets"
        action={
          <div className="flex items-center gap-2">
            <Select value={sort} onValueChange={(value) => setSort(value as SortKey)}>
              <SelectTrigger size="sm" className="h-7 w-[130px] text-[11px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="latest">Latest</SelectItem>
                <SelectItem value="confidence">Confidence</SelectItem>
                <SelectItem value="symbol">Symbol</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex items-center overflow-hidden rounded-md border border-border">
              <button
                type="button"
                onClick={() => setView("grid")}
                aria-label="Grid view"
                aria-pressed={view === "grid"}
                className={cn(
                  "px-2 py-1 transition-colors",
                  view === "grid" ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50",
                )}
              >
                <LayoutGrid className="size-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setView("list")}
                aria-label="List view"
                aria-pressed={view === "list"}
                className={cn(
                  "px-2 py-1 transition-colors",
                  view === "list" ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50",
                )}
              >
                <List className="size-3.5" />
              </button>
            </div>
          </div>
        }
        bodyClassName={view === "grid" ? "" : "p-0"}
      >
        {!demo && signals.error ? <ErrorNote>{signals.error}</ErrorNote> : null}

        {loading ? (
          <LoadingRows rows={6} />
        ) : filtered.length === 0 ? (
          <EmptyState>No analysis matches the current filters.</EmptyState>
        ) : view === "grid" ? (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {filtered.map((insight) => {
              const read = symbolReads[insight.symbol];
              const digits = decimalsForPrice(
                insight.currentPrice ?? insight.resistance ?? insight.support ?? read?.intel?.price ?? 1,
              );
              return (
                <AnalysisCard
                  key={insight.id}
                  insight={insight}
                  bars={read?.bars ?? []}
                  intel={read?.intel ?? null}
                  digits={digits}
                  onView={() => setSelected(insight)}
                />
              );
            })}
          </div>
        ) : (
          <div className="divide-y divide-border">
            {filtered.map((insight) => (
              <AnalysisRow key={insight.id} insight={insight} onView={() => setSelected(insight)} />
            ))}
          </div>
        )}
      </IntelSection>

      {/* 10 — Detail drawer (full screen on mobile) */}
      {selected ? (
        <AnalysisDetail
          insight={selected}
          bars={symbolReads[selected.symbol]?.bars ?? []}
          intel={symbolReads[selected.symbol]?.intel ?? null}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </div>
  );
}
