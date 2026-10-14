"use client";

import { cn } from "cn";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { formatPrice } from "@/lib/format";
import { recommendationTone, type Recommendation } from "@/lib/analysis-model";
import type { Bias, ConfidencePart, MarketIntel, TechnicalRow } from "@/lib/market-intel";

/** Small uppercase micro-label used across every section header. */
export function SectionLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("text-[10px] font-medium uppercase tracking-widest text-muted-foreground", className)}>
      {children}
    </span>
  );
}

/**
 * A dashboard section: a hairline-bordered panel with an uppercase heading.
 * Deliberately not a card — no shadow, no gradient, so dense analytics reads
 * as one continuous surface.
 */
export function IntelSection({
  title,
  hint,
  action,
  children,
  className,
  bodyClassName,
}: {
  title: string;
  hint?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-border bg-card/40", className)}>
      <header className="flex items-center justify-between gap-3 border-b border-border px-3 py-2">
        <div className="flex min-w-0 items-baseline gap-2">
          <SectionLabel>{title}</SectionLabel>
          {hint ? <span className="truncate text-[11px] text-muted-foreground">{hint}</span> : null}
        </div>
        {action}
      </header>
      <div className={cn("px-3 py-3", bodyClassName)}>{children}</div>
    </section>
  );
}

function TrendGlyph({ tone }: { tone: "bull" | "bear" | "flat" }) {
  if (tone === "bull") return <ArrowUpRight className="size-3.5 text-bull" />;
  if (tone === "bear") return <ArrowDownRight className="size-3.5 text-bear" />;
  return <Minus className="size-3.5 text-flat" />;
}

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

/* ------------------------------------------------------------------ *
 * Market summary: PRICE · AI SIGNAL · MARKET STRUCTURE (one strip)
 * ------------------------------------------------------------------ */

export function MarketSummary({
  displaySymbol,
  price,
  changePercent,
  marketOpen,
  intel,
  signalConfidence,
  signalBias,
  signalAge,
  recommendation = null,
  entryPrice = null,
  takeProfit = null,
  stopLoss = null,
}: {
  displaySymbol: string;
  price: number | null;
  changePercent: number | null;
  marketOpen: boolean | null;
  intel: MarketIntel;
  signalConfidence: number | null;
  signalBias: Bias;
  signalAge: string | null;
  /** Explicit trade signal from the Decision Maker; null until one exists. */
  recommendation?: Recommendation | null;
  entryPrice?: number | null;
  takeProfit?: number | null;
  stopLoss?: number | null;
}) {
  const changeTone =
    changePercent === null ? "flat" : changePercent >= 0 ? "bull" : "bear";

  return (
    <div className="grid divide-y divide-border rounded-lg border border-border bg-card/40 md:grid-cols-3 md:divide-x md:divide-y-0">
      {/* PRICE */}
      <div className="px-3 py-3">
        <div className="flex items-center gap-2">
          <SectionLabel>Price</SectionLabel>
          {marketOpen !== null ? (
            <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  marketOpen ? "bg-bull" : "bg-flat",
                )}
              />
              {marketOpen ? "Market open" : "Market closed"}
            </span>
          ) : null}
        </div>
        <div className="mt-1.5 flex items-end gap-2">
          <span className="text-[10px] text-muted-foreground">{displaySymbol}</span>
          <span className="tabular text-2xl font-semibold leading-none">
            {formatPrice(price)}
          </span>
          <span className={cn("tabular text-sm font-medium leading-none", biasClass(changeTone === "bull" ? "Bullish" : changeTone === "bear" ? "Bearish" : "Neutral"))}>
            {changePercent === null
              ? "—"
              : `${changePercent >= 0 ? "+" : ""}${changePercent.toFixed(2)}%`}
          </span>
        </div>
        <div className="mt-1 text-[11px] text-muted-foreground">24h change</div>
      </div>

      {/* AI SIGNAL */}
      <div className="px-3 py-3">
        <SectionLabel>AI signal</SectionLabel>
        <div className="mt-1.5 flex items-end gap-2">
          <span
            className={cn(
              "text-2xl font-semibold leading-none",
              recommendation ? recClass(recommendation) : biasClass(signalBias),
            )}
          >
            {signalConfidence === null
              ? "—"
              : (recommendation ?? signalBias.toUpperCase())}
          </span>
          <TrendGlyph
            tone={
              recommendation
                ? recommendationTone(recommendation)
                : signalBias === "Bullish"
                  ? "bull"
                  : signalBias === "Bearish"
                    ? "bear"
                    : "flat"
            }
          />
          {signalConfidence !== null ? (
            <span className="tabular text-sm font-medium leading-none text-muted-foreground">
              {Math.round(signalConfidence * 100)}%
            </span>
          ) : null}
        </div>
        <div className="mt-1 text-[11px] text-muted-foreground">
          {signalConfidence === null
            ? "Confidence — awaiting a signal"
            : `Confidence · ${signalAge ?? "latest"}`}
        </div>

        {/* Levels are only meaningful alongside an active directional call. */}
        {recommendation && recommendation !== "WAIT" ? (
          <div className="tabular mt-2 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px]">
            <span className="text-muted-foreground">
              Entry{" "}
              <span className="font-medium text-foreground">
                {entryPrice === null ? "—" : formatPrice(entryPrice)}
              </span>
            </span>
            <span className="text-muted-foreground">
              TP{" "}
              <span className="font-medium text-bull">
                {takeProfit === null ? "—" : formatPrice(takeProfit)}
              </span>
            </span>
            <span className="text-muted-foreground">
              SL{" "}
              <span className="font-medium text-bear">
                {stopLoss === null ? "—" : formatPrice(stopLoss)}
              </span>
            </span>
          </div>
        ) : null}
      </div>

      {/* MARKET STRUCTURE */}
      <div className="px-3 py-3">
        <SectionLabel>Market structure</SectionLabel>
        <div className="mt-1.5 flex items-end gap-2">
          <span className={cn("text-2xl font-semibold leading-none", biasClass(intel.structure))}>
            {intel.ready ? intel.structure.toUpperCase() : "—"}
          </span>
          <TrendGlyph
            tone={intel.structure === "Bullish" ? "bull" : intel.structure === "Bearish" ? "bear" : "flat"}
          />
        </div>
        <div className="mt-1 truncate text-[11px] text-muted-foreground">
          {intel.ready ? intel.structureNote : "Awaiting candle data"}
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Market conditions
 * ------------------------------------------------------------------ */

function Condition({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "bull" | "bear" | "flat";
}) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-2 px-3 py-2.5">
      <SectionLabel>{label}</SectionLabel>
      <span className="flex items-center gap-1.5">
        <span className={cn("text-sm font-medium", biasClass(tone === "bull" ? "Bullish" : tone === "bear" ? "Bearish" : "Neutral"))}>
          {value}
        </span>
        <TrendGlyph tone={tone} />
      </span>
    </div>
  );
}

export function MarketConditions({ intel }: { intel: MarketIntel }) {
  const volumeTone = intel.volume === "High" ? "bull" : intel.volume === "Low" ? "bear" : "flat";
  const volatilityTone = intel.volatility === "High" ? "bull" : intel.volatility === "Low" ? "bear" : "flat";

  return (
    <IntelSection title="Market conditions" bodyClassName="p-0">
      <div className="grid grid-cols-2 divide-x divide-y divide-border lg:grid-cols-4 lg:divide-y-0">
        <Condition
          label="Trend"
          value={intel.trend}
          tone={intel.trend === "Bullish" ? "bull" : intel.trend === "Bearish" ? "bear" : "flat"}
        />
        <Condition
          label="Momentum"
          value={intel.momentum}
          tone={
            intel.momentum === "Weak"
              ? "flat"
              : intel.structure === "Bullish"
                ? "bull"
                : "bear"
          }
        />
        <Condition label="Volatility" value={intel.volatility} tone={volatilityTone} />
        <Condition label="Volume" value={intel.volume} tone={volumeTone} />
      </div>
    </IntelSection>
  );
}

/* ------------------------------------------------------------------ *
 * Technical analysis
 * ------------------------------------------------------------------ */

export function TechnicalAnalysis({ rows }: { rows: TechnicalRow[] }) {
  if (!rows.length) {
    return (
      <IntelSection title="Technical analysis">
        <p className="text-xs text-muted-foreground">
          Indicators appear once enough candles have loaded.
        </p>
      </IntelSection>
    );
  }
  return (
    <IntelSection title="Technical analysis" bodyClassName="p-0">
      <div className="grid grid-cols-2 divide-x divide-y divide-border sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
        {rows.map((row) => (
          <div key={row.label} className="px-3 py-2.5">
            <SectionLabel>{row.label}</SectionLabel>
            <div className="mt-1 flex items-center gap-1.5">
              <span className={cn("tabular text-sm font-medium", biasClass(row.state as Bias))}>
                {row.value}
              </span>
              <TrendGlyph
                tone={
                  row.tone === "bull" ? "bull" : row.tone === "bear" ? "bear" : "flat"
                }
              />
            </div>
          </div>
        ))}
      </div>
    </IntelSection>
  );
}

/* ------------------------------------------------------------------ *
 * Multi-timeframe
 * ------------------------------------------------------------------ */

export function MultiTimeframe({
  frames,
  active,
  onSelect,
}: {
  frames: Array<{ value: string; label: string; bias: Bias; score: number }>;
  active: string;
  onSelect: (value: string) => void;
}) {
  return (
    <IntelSection
      title="Multi-timeframe"
      hint="Select a timeframe to re-analyse"
      bodyClassName="p-0"
    >
      <div className="flex overflow-x-auto">
        {frames.map((frame) => {
          const selected = frame.value === active;
          const tone =
            frame.bias === "Bullish" ? "bull" : frame.bias === "Bearish" ? "bear" : "flat";
          return (
            <button
              key={frame.value}
              type="button"
              onClick={() => onSelect(frame.value)}
              aria-pressed={selected}
              className={cn(
                "flex min-w-[110px] flex-1 flex-col items-start gap-1 border-r border-border px-3 py-2.5 text-left transition-colors last:border-r-0",
                selected ? "bg-accent/60" : "hover:bg-accent/30",
              )}
            >
              <span className="flex items-center gap-1.5">
                <SectionLabel>{frame.label}</SectionLabel>
                <TrendGlyph tone={tone} />
              </span>
              <span className={cn("text-sm font-medium", biasClass(frame.bias))}>
                {frame.bias}
              </span>
              <span className="tabular text-[11px] text-muted-foreground">
                {Math.round(frame.score * 100)}% read
              </span>
            </button>
          );
        })}
      </div>
    </IntelSection>
  );
}

/* ------------------------------------------------------------------ *
 * Confidence breakdown
 * ------------------------------------------------------------------ */

export function ConfidenceBreakdown({
  parts,
  overall,
}: {
  parts: ConfidencePart[];
  overall: number;
}) {
  return (
    <div className="space-y-2">
      {parts.map((part) => (
        <div key={part.label} className="space-y-1">
          <div className="flex items-center justify-between text-xs">
            <span className={cn("text-muted-foreground", part.pending && "italic")}>
              {part.label}
            </span>
            <span className="tabular text-muted-foreground">
              {part.pending ? "pending" : `${Math.round(part.value * 100)}%`}
            </span>
          </div>
          <div className="h-1 overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                "h-full rounded-full transition-all",
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
        <span className="tabular font-medium">{Math.round(overall * 100)}%</span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Signal history
 * ------------------------------------------------------------------ */

export function SignalHistory({
  entries,
  filter,
  onFilterChange,
}: {
  entries: Array<{ id: string; bias: Bias; confidence: number; time: string }>;
  filter: "All" | "Bullish" | "Bearish";
  onFilterChange: (filter: "All" | "Bullish" | "Bearish") => void;
}) {
  const visible = entries.filter((entry) => {
    if (filter === "Bullish") return entry.bias === "Bullish";
    if (filter === "Bearish") return entry.bias === "Bearish";
    return true;
  });

  return (
    <IntelSection
      title="Signal history"
      hint={`${entries.length} recorded`}
      action={
        <div className="flex items-center gap-1">
          {(["All", "Bullish", "Bearish"] as const).map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => onFilterChange(option)}
              aria-pressed={filter === option}
              className={cn(
                "rounded px-2 py-1 text-[11px] transition-colors",
                filter === option
                  ? "bg-accent text-foreground"
                  : "text-muted-foreground hover:bg-accent/50",
              )}
            >
              {option}
            </button>
          ))}
        </div>
      }
      bodyClassName="p-0"
    >
      {visible.length === 0 ? (
        <p className="px-3 py-3 text-xs text-muted-foreground">
          No signals recorded for this market yet.
        </p>
      ) : (
        <ul className="max-h-64 divide-y divide-border overflow-y-auto">
          {visible.slice(0, 20).map((entry) => (
            <li key={entry.id} className="flex items-center gap-3 px-3 py-1.5 text-xs">
              <span className="tabular w-14 shrink-0 text-muted-foreground">{entry.time}</span>
              <span
                className={cn(
                  "flex items-center gap-1.5 font-medium",
                  biasClass(entry.bias),
                )}
              >
                <TrendGlyph
                  tone={
                    entry.bias === "Bullish" ? "bull" : entry.bias === "Bearish" ? "bear" : "flat"
                  }
                />
                {entry.bias.toUpperCase()}
              </span>
              <span className="tabular ml-auto text-muted-foreground">
                {Math.round(entry.confidence * 100)}%
              </span>
            </li>
          ))}
        </ul>
      )}
    </IntelSection>
  );
}

/* ------------------------------------------------------------------ *
 * Level chip used by the AI analysis panel
 * ------------------------------------------------------------------ */

export function LevelMeter({ levels, digits }: { levels: MarketIntel["levels"]; digits: number }) {
  if (!levels.length) return null;
  const prices = levels.map((level) => level.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = max - min || 1;

  return (
    <ul className="space-y-1.5">
      {levels.map((level) => {
        const offset = Math.round(((level.price - min) / span) * 100);
        return (
          <li key={level.label} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">{level.label}</span>
              <span className="tabular font-medium">{formatPrice(level.price, digits)}</span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full",
                  level.tone === "bull" ? "bg-bull" : level.tone === "bear" ? "bg-bear" : "bg-foreground",
                )}
                style={{ width: `${Math.max(4, 100 - offset)}%` }}
              />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
