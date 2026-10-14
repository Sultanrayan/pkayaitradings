"use client";

import { useRouter } from "next/navigation";
import { Check, MessageSquareText, X } from "lucide-react";
import { cn } from "cn";

import { SectionLabel } from "@/components/dashboard/intel-sections";
import { Button } from "@/components/ui/button";
import { decimalsForPrice, formatPrice } from "@/lib/format";
import type { AnalysisInsight, Bias, Recommendation } from "@/lib/analysis-model";
import type { ConfidencePart, MarketIntel } from "@/lib/market-intel";
import type { OhlcBar } from "@/lib/types";

function biasClass(bias: Bias): string {
  if (bias === "Bullish") return "text-bull";
  if (bias === "Bearish") return "text-bear";
  return "text-flat";
}

function recClass(recommendation: Recommendation): string {
  if (recommendation === "BUY") return "text-bull";
  if (recommendation === "SELL") return "text-bear";
  return "text-flat";
}

/** One trade level in the detail header. */
function DetailLevel({
  label,
  value,
  className,
}: {
  label: string;
  value: number | null;
  className?: string;
}) {
  return (
    <div className="rounded border border-border px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className={cn("text-xs font-medium", value === null ? "text-muted-foreground/50" : className)}>
        {value === null ? "—" : formatPrice(value)}
      </div>
    </div>
  );
}

function Block({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-border px-4 py-3">
      <SectionLabel>{title}</SectionLabel>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function TechnicalLine({
  label,
  value,
  bias,
}: {
  label: string;
  value: string;
  bias?: Bias;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="flex items-center gap-2">
        <span className="tabular text-xs font-medium">{value}</span>
        {bias ? (
          <span className={cn("text-[10px] uppercase", biasClass(bias))}>{bias}</span>
        ) : null}
      </span>
    </div>
  );
}

function LevelLine({ label, value, digits }: { label: string; value: number | null; digits: number }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="tabular text-xs font-medium">
        {value === null ? "—" : formatPrice(value, digits)}
      </span>
    </div>
  );
}

/**
 * Analysis detail — a right-hand drawer (full screen on mobile). Opens over
 * the feed without navigating away.
 */
export function AnalysisDetail({
  insight,
  bars,
  intel,
  onClose,
}: {
  insight: AnalysisInsight | null;
  bars: OhlcBar[];
  intel: MarketIntel | null;
  onClose: () => void;
}) {
  const router = useRouter();

  if (!insight) return null;

  const confidencePct = Math.round(insight.confidence * 100);
  const digits = decimalsForPrice(
    insight.currentPrice ?? insight.resistance ?? insight.support ?? 1,
  );

  const reasons = intel?.reasons.length ? intel.reasons : insight.reasons;
  const resistance = insight.resistance ?? intel?.levels.find((l) => l.label === "Resistance")?.price ?? null;
  const currentPrice = insight.currentPrice ?? intel?.levels.find((l) => l.label === "Current price")?.price ?? intel?.price ?? null;
  const support = insight.support ?? intel?.levels.find((l) => l.label === "Support")?.price ?? null;

  // Technical readout: real indicator values when candles are loaded.
  const technicalRows: Array<{ label: string; value: string; bias?: Bias }> = [];
  if (intel?.rsi !== null && intel?.rsi !== undefined) {
    technicalRows.push({
      label: "RSI",
      value: intel.rsi.toFixed(0),
      bias: intel.rsi >= 55 ? "Bullish" : intel.rsi <= 45 ? "Bearish" : "Neutral",
    });
  }
  if (intel?.macdHistogram !== null && intel?.macdHistogram !== undefined) {
    technicalRows.push({
      label: "MACD",
      value: intel.macdHistogram >= 0 ? "Positive" : "Negative",
      bias: intel.macdHistogram >= 0 ? "Bullish" : "Bearish",
    });
  }
  if (intel?.ema20 !== null && intel?.ema20 !== undefined) {
    technicalRows.push({
      label: "EMA 20",
      value: formatPrice(intel.ema20, digits),
      bias: intel.price && intel.price > intel.ema20 ? "Bullish" : "Bearish",
    });
  }
  if (intel?.ema50 !== null && intel?.ema50 !== undefined) {
    technicalRows.push({
      label: "EMA 50",
      value: formatPrice(intel.ema50, digits),
      bias: intel.price && intel.price > intel.ema50 ? "Bullish" : "Bearish",
    });
  }
  if (intel?.volumeChangePercent !== null && intel?.volumeChangePercent !== undefined) {
    technicalRows.push({
      label: "Volume",
      value: `${intel.volumeChangePercent >= 0 ? "+" : ""}${intel.volumeChangePercent.toFixed(0)}%`,
      bias: intel.volume === "High" ? "Bullish" : intel.volume === "Low" ? "Bearish" : "Neutral",
    });
  }

  const breakdown: ConfidencePart[] = intel?.breakdown ?? [
    { label: "Technical analysis", value: insight.confidence },
    { label: "Momentum", value: insight.confidence },
    { label: "Volume", value: insight.confidence },
    { label: "Market sentiment", value: insight.confidence },
  ];

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="Close analysis"
        onClick={onClose}
        className="absolute inset-0 bg-background/70 backdrop-blur-sm"
      />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="AI market analysis"
        className="relative flex h-full w-full max-w-lg flex-col overflow-y-auto border-l border-border bg-background"
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-2 border-b border-border px-4 py-3">
          <div>
            <SectionLabel>AI market analysis</SectionLabel>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <span className="text-sm font-medium">
                {insight.symbol} · {insight.timeframe ?? "—"}
              </span>
              <span
                className={cn(
                  "rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground",
                  insight.bias === "Bullish"
                    ? "bg-bull/10 text-bull"
                    : insight.bias === "Bearish"
                      ? "bg-bear/10 text-bear"
                      : "bg-muted text-muted-foreground",
                )}
              >
                {insight.bias}
              </span>
            </div>
          </div>
          <Button variant="ghost" size="icon-sm" aria-label="Close analysis" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        <div className="border-b border-border px-4 py-3">
          <div
            className={cn(
              "text-2xl font-semibold leading-none",
              insight.recommendation ? recClass(insight.recommendation) : biasClass(insight.bias),
            )}
          >
            {insight.recommendation ?? insight.bias.toUpperCase()}
          </div>
          <div className="mt-1.5 flex items-center gap-2">
            <span className="tabular text-sm font-medium">{confidencePct}% confidence</span>
            <span className="h-1 w-28 overflow-hidden rounded-full bg-muted">
              <span
                className={cn(
                  "block h-full rounded-full",
                  insight.bias === "Bullish"
                    ? "bg-bull"
                    : insight.bias === "Bearish"
                      ? "bg-bear"
                      : "bg-flat",
                )}
                style={{ width: `${confidencePct}%` }}
              />
            </span>
          </div>

          {/* Trade levels, shown only for an active directional call. */}
          {insight.recommendation && insight.recommendation !== "WAIT" ? (
            <div className="tabular mt-3 grid grid-cols-3 gap-2">
              <DetailLevel label="Entry" value={insight.entryPrice} />
              <DetailLevel label="Take profit" value={insight.takeProfit} className="text-bull" />
              <DetailLevel label="Stop loss" value={insight.stopLoss} className="text-bear" />
            </div>
          ) : null}
        </div>

        <Block title="AI summary">
          <p className="text-sm leading-relaxed">
            {insight.summary ??
              `${insight.symbol} reads ${insight.bias.toLowerCase()} on the ${insight.timeframe ?? "current"} timeframe.`}
          </p>
          <p className="mt-1.5 text-[11px] text-muted-foreground">
            {insight.agent} · {insight.agentDescription}
          </p>
        </Block>

        <Block title="Why?">
          {reasons.length === 0 ? (
            <p className="text-xs italic text-muted-foreground/70">
              Indicator evidence arrives with the next analysis cycle.
            </p>
          ) : (
            <ul className="space-y-1">
              {reasons.map((reason) => (
                <li key={reason} className="flex gap-2 text-xs leading-relaxed text-muted-foreground">
                  <Check className="mt-0.5 size-3 shrink-0 text-bull" />
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          )}
        </Block>

        <Block title="Technical analysis">
          {technicalRows.length === 0 ? (
            <p className="text-xs italic text-muted-foreground/70">
              Indicators appear once candles have loaded.
            </p>
          ) : (
            <div className="divide-y divide-border/60">
              {technicalRows.map((row) => (
                <TechnicalLine key={row.label} {...row} />
              ))}
            </div>
          )}
        </Block>

        <Block title="Key levels">
          <div className="divide-y divide-border/60">
            <LevelLine label="Resistance" value={resistance} digits={digits} />
            <LevelLine label="Current" value={currentPrice} digits={digits} />
            <LevelLine label="Support" value={support} digits={digits} />
          </div>
        </Block>

        <Block title="AI confidence">
          <div className="space-y-2">
            {breakdown.map((part) => (
              <div key={part.label} className="space-y-1">
                <div className="flex items-center justify-between text-[11px]">
                  <span className="text-muted-foreground">{part.label}</span>
                  <span className="tabular text-muted-foreground">
                    {part.pending ? "pending" : `${Math.round(part.value * 100)}%`}
                  </span>
                </div>
                <div className="h-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn(
                      "h-full rounded-full",
                      part.pending
                        ? "bg-muted-foreground/30"
                        : part.value >= 0.55
                          ? "bg-bull"
                          : part.value <= 0.45
                            ? "bg-bear"
                            : "bg-foreground",
                    )}
                    style={{ width: `${Math.round(part.value * 100)}%` }}
                  />
                </div>
              </div>
            ))}
            <div className="flex items-center justify-between border-t border-border pt-2 text-xs">
              <span className="font-medium">Overall</span>
              <span className="tabular font-medium">{confidencePct}%</span>
            </div>
          </div>
        </Block>

        <div className="border-t border-border px-4 py-3">
          <Button
            className="w-full gap-1.5"
            onClick={() => router.push("/ai")}
          >
            <MessageSquareText className="size-4" />
            Ask AI About This Analysis
          </Button>
        </div>

        {bars.length === 0 ? (
          <p className="px-4 pb-4 text-[11px] text-muted-foreground">
            Market conditions are derived from live candles once available.
          </p>
        ) : null}
      </aside>
    </div>
  );
}
