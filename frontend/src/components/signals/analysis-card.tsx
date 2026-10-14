"use client";

import { useId } from "react";
import { ArrowDownRight, ArrowRight, ArrowUpRight, Minus } from "lucide-react";
import { cn } from "cn";

import { SectionLabel } from "@/components/dashboard/intel-sections";
import { formatDateTime, formatPrice } from "@/lib/format";
import type { AnalysisInsight, Bias, Recommendation } from "@/lib/analysis-model";
import type { MarketIntel } from "@/lib/market-intel";
import type { OhlcBar } from "@/lib/types";

function biasClass(bias: Bias): string {
  if (bias === "Bullish") return "text-bull";
  if (bias === "Bearish") return "text-bear";
  return "text-flat";
}

function recommendationClass(recommendation: Recommendation): string {
  if (recommendation === "BUY") return "bg-bull/15 text-bull";
  if (recommendation === "SELL") return "bg-bear/15 text-bear";
  return "bg-flat/15 text-flat";
}

/** One cell of the entry / target / stop strip. Renders an em dash when absent. */
function LevelCell({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | null;
  tone?: "bull" | "bear";
}) {
  return (
    <div className="px-1 py-1.5">
      <div className="text-[9px] uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div
        className={cn(
          "tabular text-[11px] font-medium",
          value === null ? "text-muted-foreground/50" : tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-foreground",
        )}
      >
        {value === null ? "—" : formatPrice(value)}
      </div>
    </div>
  );
}

function BiasGlyph({ bias }: { bias: Bias }) {
  if (bias === "Bullish") return <ArrowUpRight className="size-3.5" />;
  if (bias === "Bearish") return <ArrowDownRight className="size-3.5" />;
  return <Minus className="size-3.5" />;
}

/** Catmull-rom → cubic-bezier smoothing through the given points. */
function smoothPath(points: Array<[number, number]>): string {
  if (points.length < 2) return "";
  let d = `M ${points[0][0]},${points[0][1]}`;
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    d += ` C ${c1x.toFixed(2)},${c1y.toFixed(2)} ${c2x.toFixed(2)},${c2y.toFixed(2)} ${p2[0].toFixed(2)},${p2[1].toFixed(2)}`;
  }
  return d;
}

/**
 * Mini price chart from real candles — shows recent price movement only. It
 * is drawn as a plain area/line with no projection beyond the last close.
 */
function MiniChart({ bars, bias }: { bars: OhlcBar[]; bias: Bias }) {
  const gradientId = useId().replace(/:/g, "");
  const values = bars.slice(-32).map((bar) => bar.close);

  if (values.length < 2) {
    return (
      <div className="flex h-16 items-center justify-center text-[11px] text-muted-foreground">
        Loading price history…
      </div>
    );
  }

  const color = bias === "Bullish" ? "var(--bull)" : bias === "Bearish" ? "var(--bear)" : "var(--flat)";
  const width = 260;
  const height = 64;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padX = 4;
  const padY = 6;
  const step = (width - padX * 2) / (values.length - 1);
  const coords = values.map((value, index) => [
    padX + index * step,
    height - padY - ((value - min) / range) * (height - padY * 2),
  ]) as Array<[number, number]>;
  const line = smoothPath(coords);
  const area = `${line} L ${coords[coords.length - 1][0]},${height} L ${coords[0][0]},${height} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-16 w-full"
      role="img"
      aria-label="Recent price movement"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.26" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function ConditionRow({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className={cn("text-[11px] font-medium", value ? "text-foreground" : "text-muted-foreground/60")}>
        {value ?? "—"}
      </span>
    </div>
  );
}

function LevelRow({ label, value, digits }: { label: string; value: number | null; digits: number }) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="tabular text-[11px] font-medium">
        {value === null ? "—" : formatPrice(value, digits)}
      </span>
    </div>
  );
}

/**
 * One analytical insight. Shows market bias, confidence, the reasoning, the
 * evidence behind it, current conditions and key levels — no trade setup.
 */
export function AnalysisCard({
  insight,
  bars,
  intel,
  digits,
  onView,
}: {
  insight: AnalysisInsight;
  bars: OhlcBar[];
  intel: MarketIntel | null;
  digits: number;
  onView: () => void;
}) {
  const confidencePct = Math.round(insight.confidence * 100);

  // Prefer evidence derived from real candles; fall back to the payload.
  const reasons = intel?.reasons.length ? intel.reasons : insight.reasons;
  const trend = insight.trend ?? intel?.trend ?? null;
  const momentum = insight.momentum ?? intel?.momentum ?? null;
  const volatility = insight.volatility ?? intel?.volatility ?? null;
  const volume =
    insight.volume ??
    (intel?.volumeChangePercent !== null && intel?.volumeChangePercent !== undefined
      ? `${intel.volumeChangePercent >= 0 ? "+" : ""}${intel.volumeChangePercent.toFixed(0)}%`
      : null);

  const resistance = insight.resistance ?? intel?.levels.find((l) => l.label === "Resistance")?.price ?? null;
  const currentPrice =
    insight.currentPrice ??
    intel?.levels.find((l) => l.label === "Current price")?.price ??
    intel?.price ??
    null;
  const support = insight.support ?? intel?.levels.find((l) => l.label === "Support")?.price ?? null;

  return (
    <article className="flex flex-col overflow-hidden rounded-lg border border-border bg-card/40 transition-colors hover:border-foreground/20">
      {/* Header */}
      <header className="flex items-start justify-between gap-2 border-b border-border px-3 py-2.5">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-medium">{insight.symbol}</span>
            {insight.timeframe ? (
              <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                {insight.timeframe}
              </span>
            ) : null}
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
              {insight.analysisType}
            </span>
          </div>
          <time className="mt-1 block text-[10px] text-muted-foreground">
            {formatDateTime(insight.timestamp)}
          </time>
        </div>
        <div className="shrink-0 text-right">
          {insight.recommendation ? (
            <div
              className={cn(
                "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-xs font-semibold",
                recommendationClass(insight.recommendation),
              )}
            >
              {insight.recommendation}
            </div>
          ) : (
            <div className={cn("flex items-center justify-end gap-1 text-sm font-semibold", biasClass(insight.bias))}>
              <BiasGlyph bias={insight.bias} />
              {insight.bias.toUpperCase()}
            </div>
          )}
          <div className="tabular mt-0.5 text-[11px] text-muted-foreground">
            {confidencePct}% confidence
          </div>
        </div>
      </header>

      {/* Trade levels — only the Decision Maker emits a recommendation, so this
          strip appears on its cards and is omitted everywhere else. */}
      {insight.recommendation && insight.recommendation !== "WAIT" ? (
        <div className="grid grid-cols-3 divide-x divide-border border-b border-border text-center">
          <LevelCell label="Entry" value={insight.entryPrice} />
          <LevelCell label="Target" value={insight.takeProfit} tone="bull" />
          <LevelCell label="Stop" value={insight.stopLoss} tone="bear" />
        </div>
      ) : null}

      {/* Confidence bar */}
      <div className="h-0.5 w-full bg-muted">
        <div
          className={cn(
            "h-full",
            insight.bias === "Bullish"
              ? "bg-bull"
              : insight.bias === "Bearish"
                ? "bg-bear"
                : "bg-flat",
          )}
          style={{ width: `${confidencePct}%` }}
        />
      </div>

      {/* Mini chart */}
      <div className="px-1 py-1.5">
        <MiniChart bars={bars} bias={insight.bias} />
      </div>

      {/* AI view */}
      <div className="space-y-1.5 border-t border-border px-3 py-2.5">
        <SectionLabel>AI view</SectionLabel>
        <p className="text-xs leading-relaxed text-muted-foreground">
          {insight.summary ??
            `${insight.symbol} reads ${insight.bias.toLowerCase()} on the ${insight.timeframe ?? "current"} timeframe.`}
        </p>
      </div>

      {/* Why */}
      <div className="space-y-1 border-t border-border px-3 py-2.5">
        <SectionLabel>Why?</SectionLabel>
        {reasons.length === 0 ? (
          <p className="text-[11px] italic text-muted-foreground/70">
            Indicator evidence arrives with the next analysis cycle.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {reasons.map((reason) => (
              <li key={reason} className="flex gap-1.5 text-[11px] leading-relaxed text-muted-foreground">
                <span className="text-bull">✓</span>
                <span>{reason}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Conditions + levels */}
      <div className="grid grid-cols-2 gap-3 border-t border-border px-3 py-2.5">
        <div>
          <SectionLabel>Market conditions</SectionLabel>
          <div className="mt-1">
            <ConditionRow label="Trend" value={trend} />
            <ConditionRow label="Momentum" value={momentum} />
            <ConditionRow label="Volatility" value={volatility} />
            <ConditionRow label="Volume" value={volume} />
          </div>
        </div>
        <div>
          <SectionLabel>Key levels</SectionLabel>
          <div className="mt-1">
            <LevelRow label="Resistance" value={resistance} digits={digits} />
            <LevelRow label="Current price" value={currentPrice} digits={digits} />
            <LevelRow label="Support" value={support} digits={digits} />
          </div>
        </div>
      </div>

      {/* Agent + action */}
      <footer className="mt-auto flex items-center gap-2 border-t border-border px-3 py-2">
        <div className="min-w-0">
          <div className="truncate text-[11px] font-medium">AI agent</div>
          <div className="truncate text-[10px] text-muted-foreground">
            {insight.agent} · {insight.agentDescription}
          </div>
        </div>
        <button
          type="button"
          onClick={onView}
          className="ml-auto inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-1 text-[11px] font-medium text-foreground/80 transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          View Analysis
          <ArrowRight className="size-3" />
        </button>
      </footer>
    </article>
  );
}

/** Compact single-row variant for the list view. */
export function AnalysisRow({
  insight,
  onView,
}: {
  insight: AnalysisInsight;
  onView: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onView}
      className="flex w-full flex-wrap items-center gap-3 border-b border-border px-3 py-2 text-left transition-colors last:border-b-0 hover:bg-accent/40"
    >
      <span className="text-sm font-medium">{insight.symbol}</span>
      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
        {insight.timeframe ?? "—"}
      </span>
      <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
        {insight.analysisType}
      </span>
      <span className={cn("flex items-center gap-1 text-xs font-medium", biasClass(insight.bias))}>
        <BiasGlyph bias={insight.bias} />
        {insight.bias.toUpperCase()}
      </span>
      <span className="tabular text-xs text-muted-foreground">
        {Math.round(insight.confidence * 100)}%
      </span>
      <span className="truncate text-xs text-muted-foreground">{insight.summary}</span>
      <span className="ml-auto text-[10px] text-muted-foreground">{insight.agent}</span>
    </button>
  );
}
