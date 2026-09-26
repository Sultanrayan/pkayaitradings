"use client";

import { useId } from "react";
import { cn } from "cn";

import { useMarketSnapshot } from "@/hooks/use-market-snapshot";
import {
  decimalsForPrice,
  formatPrice,
  formatSignedPercent,
} from "@/lib/format";

/** Deterministic sparkline series for a symbol, stable per session. */
function seriesFor(symbol: string, count = 32): number[] {
  let hash = 2166136261;
  for (let i = 0; i < symbol.length; i += 1) {
    hash ^= symbol.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  let seed = hash >>> 0;
  const rand = () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const bullish = rand() > 0.35;
  const values: number[] = [];
  let v = 0.5 + rand() * 0.5;
  for (let i = 0; i < count; i += 1) {
    const drift = (bullish ? 0.02 : -0.015) + (rand() - 0.5) * 0.09;
    v = Math.max(0.02, v + drift);
    values.push(v);
  }
  return values;
}

export function Sparkline({
  values,
  tone = "neutral",
  height = 40,
  className,
}: {
  values?: number[];
  tone?: "up" | "down" | "neutral";
  height?: number;
  className?: string;
}) {
  const gradientId = useId().replace(/:/g, "");
  const raw = values ?? seriesFor("spark", 32);
  if (raw.length < 2) return null;
  const min = Math.min(...raw);
  const max = Math.max(...raw);
  const range = max - min || 1;
  const color = tone === "up" ? "var(--bull)" : tone === "down" ? "var(--bear)" : "var(--flat)";
  const width = 120;
  const pad = 2;
  const step = (width - pad * 2) / (raw.length - 1);
  const coords = raw.map((value, index) => [
    pad + index * step,
    height - pad - ((value - min) / range) * (height - pad * 2),
  ]);
  const line = coords
    .map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ");
  const area = `${line} L${coords[coords.length - 1][0].toFixed(1)},${height} L${coords[0][0].toFixed(1)},${height} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={cn("h-full w-full", className)}
      aria-hidden
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} />
      <path
        d={line}
        fill="none"
        stroke={color}
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function MarketAttachment({
  symbol,
  onClick,
}: {
  symbol: string;
  onClick?: () => void;
}) {
  const { price, change, source } = useMarketSnapshot(symbol);
  const tone = change >= 0 ? "up" : "down";
  const digits = decimalsForPrice(price);
  const isUp = change >= 0;

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full overflow-hidden rounded-lg border border-border bg-card text-left transition-colors hover:border-foreground/30"
    >
      <div className="flex items-start justify-between gap-3 p-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase">
              {symbol}
            </span>
            <span className="text-[11px] text-muted-foreground">
              {source === "live" ? "Live" : "Demo"} market
            </span>
          </div>
          <div className="mt-1.5 truncate text-base font-semibold tabular">
            {formatPrice(price, digits)}
          </div>
          <div
            className={cn(
              "tabular text-xs font-medium",
              isUp ? "text-bull" : "text-bear",
            )}
          >
            {formatSignedPercent(change)}
            <span className="ml-1 font-normal text-muted-foreground">today</span>
          </div>
        </div>
        <div className="h-10 w-28 shrink-0">
          <Sparkline values={seriesFor(symbol)} tone={tone} />
        </div>
      </div>
    </button>
  );
}

export function ChartAttachment({
  symbol,
  timeframe,
  onClick,
}: {
  symbol: string;
  timeframe: string;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full overflow-hidden rounded-lg border border-border bg-card text-left transition-colors hover:border-foreground/30"
    >
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase">
            {symbol}
          </span>
          <span className="text-[10px] text-muted-foreground">{timeframe} chart</span>
        </div>
        <span className="text-[11px] text-muted-foreground">Indicators · EMAs</span>
      </div>
      <div className="h-24 w-full bg-muted/30">
        <svg viewBox="0 0 200 96" preserveAspectRatio="none" className="size-full" aria-hidden>
          {/* mini candle body using deterministic series derived from symbol+timeframe */}
          <rect x="16" y="26" width="10" height="22" rx="1" fill="var(--bull)" opacity="0.85" />
          <rect x="46" y="18" width="10" height="38" rx="1" fill="var(--bull)" opacity="0.85" />
          <rect x="76" y="32" width="10" height="18" rx="1" fill="var(--bear)" opacity="0.85" />
          <rect x="106" y="24" width="10" height="30" rx="1" fill="var(--bull)" opacity="0.85" />
          <rect x="136" y="14" width="10" height="40" rx="1" fill="var(--bull)" opacity="0.85" />
          <rect x="166" y="30" width="10" height="20" rx="1" fill="var(--bear)" opacity="0.85" />
          {[16, 46, 76, 106, 136, 166].map((x, i) => (
            <line
              key={x}
              x1={x + 5}
              y1={i % 3 === 0 ? 10 : 8 + i * 4}
              x2={x + 5}
              y2={i % 2 === 0 ? 86 : 90 - i * 4}
              stroke="var(--muted-foreground)"
              strokeWidth="1"
              opacity="0.4"
            />
          ))}
          <path
            d="M0,70 C30,62 55,50 90,44 C130,38 160,30 200,22"
            fill="none"
            stroke="var(--chart-4)"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
    </button>
  );
}

export function SignalAttachment({
  symbol,
  side,
  timeframe,
  entry,
  target,
  stop,
  createdAt,
  onClick,
}: {
  symbol: string;
  side: "BUY" | "SELL";
  timeframe: string;
  entry: number;
  target: number;
  stop: number;
  createdAt: string;
  onClick?: () => void;
}) {
  const up = side === "BUY";
  const digits = decimalsForPrice(entry);
  const row = (label: string, value: string, className?: string) => (
    <div className="flex items-center justify-between py-1">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className={cn("tabular text-xs font-medium", className)}>{value}</span>
    </div>
  );

  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full overflow-hidden rounded-lg border border-border bg-card text-left transition-colors hover:border-foreground/30"
    >
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase">
            {symbol}
          </span>
          <span className={cn("text-[10px] font-bold uppercase", up ? "text-bull" : "text-bear")}>
            {side}
          </span>
          <span className="text-[10px] text-muted-foreground">{timeframe}</span>
        </div>
        <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
          Signal · informational
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 px-3 py-2">
        <div className="border-b border-border/50">
          {row("Entry", formatPrice(entry, digits))}
        </div>
        <div className="border-b border-border/50">
          {row("Target", formatPrice(target, digits), up ? "text-bull" : "text-bear")}
        </div>
        <div className="border-b border-border/50">
          {row("Stop loss", formatPrice(stop, digits), "text-bear")}
        </div>
        <div>
          {row("Signal", relativeDateTime(createdAt))}
        </div>
      </div>
    </button>
  );
}

function relativeDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("en-US", { hour12: false });
  } catch {
    return iso;
  }
}