"use client";

import { useId } from "react";
import { TrendingUp } from "lucide-react";
import { cn } from "cn";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { agentName } from "@/lib/constants";
import { decimalsForPrice, directionTone, formatDateTime, formatPrice } from "@/lib/format";
import {
  signalDirectionSign,
  signalLevels,
  signalReference,
  signalSeriesValues,
} from "@/lib/signal-model";
import type { SignalRecord } from "@/lib/types";

/** Smooth catmull-rom → cubic-bezier path through the given points. */
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

function Sparkline({ record }: { record: SignalRecord }) {
  const gradientId = useId().replace(/:/g, "");
  const values = signalSeriesValues(record, 24);
  if (values.length < 2) return null;
  const tone = directionTone(record.direction);
  const color =
    tone === "bull" ? "var(--bull)" : tone === "bear" ? "var(--bear)" : "var(--flat)";

  const width = 240;
  const height = 64;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padX = 6;
  const padY = 6;
  const step = (width - padX * 2) / (values.length - 1);
  const coords: Array<[number, number]> = values.map((value, i) => [
    padX + i * step,
    height - padY - ((value - min) / range) * (height - padY * 2),
  ]);
  const line = smoothPath(coords);
  const area = `${line} L ${coords[coords.length - 1][0]},${height} L ${coords[0][0]},${height} Z`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-full w-full"
      aria-hidden
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.30" />
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

function LevelCell({
  label,
  value,
  empty,
}: {
  label: string;
  value: string;
  empty: boolean;
}) {
  return (
    <div className="flex flex-col items-center gap-0.5 py-2.5">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={cn("tabular text-[13px] font-semibold", empty && "text-muted-foreground/60")}>
        {value}
      </span>
    </div>
  );
}

/**
 * One signal card: mini sparkline on top, trade-plan levels (Entry / SL / TP1 /
 * TP2) and a confidence bar below. Clicking opens the detail dialog.
 */
export function SignalCard({
  record,
  onSelect,
}: {
  record: SignalRecord;
  onSelect: (record: SignalRecord) => void;
}) {
  const levels = signalLevels(record);
  const digits = decimalsForPrice(signalReference(record));
  const price = (value: number | null) =>
    value == null ? "—" : formatPrice(value, digits);
  const sign = signalDirectionSign(record);
  const tone = directionTone(record.direction);
  const confidencePct = Math.round(Math.min(Math.max(levels.confidence, 0), 1) * 100);

  return (
    <button
      type="button"
      onClick={() => onSelect(record)}
      className="group flex h-full flex-col overflow-hidden rounded-xl bg-card text-left ring-1 ring-foreground/10 transition-colors hover:ring-foreground/30 focus-visible:ring-2 focus-visible:ring-ring"
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2 px-3.5 pt-3">
        <div className="flex min-w-0 items-center gap-2">
          <Badge variant="outline" className="shrink-0 text-[10px]">
            {record.symbol}
          </Badge>
          <span
            className={cn(
              "truncate text-xs font-medium capitalize",
              tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-muted-foreground",
            )}
          >
            {sign > 0 ? "▲" : sign < 0 ? "▼" : "•"} {record.direction.toLowerCase()}
          </span>
        </div>
        <span className="shrink-0 text-[10px] text-muted-foreground">
          {formatDateTime(record.created_at)}
        </span>
      </div>

      {/* Line graph */}
      <div className="mt-2 h-16 w-full px-1.5">
        <Sparkline record={record} />
      </div>

      {/* Entry / SL / TP1 / TP2 */}
      <div className="mt-2 grid grid-cols-4 divide-x divide-border border-y border-border">
        <LevelCell label="Entry" value={price(levels.entry)} empty={levels.entry == null} />
        <LevelCell label="SL" value={price(levels.sl)} empty={levels.sl == null} />
        <LevelCell label="TP1" value={price(levels.tp1)} empty={levels.tp1 == null} />
        <LevelCell label="TP2" value={price(levels.tp2)} empty={levels.tp2 == null} />
      </div>

      {/* Confidence */}
      <div className="mt-2.5 flex items-center gap-2 px-3.5 pb-3">
        <span className="whitespace-nowrap text-[10px] uppercase tracking-wider text-muted-foreground">
          Confidence
        </span>
        <Progress
          value={confidencePct}
          className="h-1.5 flex-1 bg-muted"
          indicatorClassName={tone === "bull" ? "bg-bull" : tone === "bear" ? "bg-bear" : "bg-flat"}
        />
        <span className="tabular whitespace-nowrap text-[11px] text-muted-foreground">
          {confidencePct}%
        </span>
      </div>

      <div className="mt-auto flex items-center gap-1.5 border-t border-border bg-muted/40 px-3.5 py-2 text-[10px] text-muted-foreground">
        <TrendingUp className="size-3" />
        <span className="truncate">{agentName(record.agent)}</span>
        <span className="ml-auto shrink-0 font-medium text-foreground/70 transition-colors group-hover:text-foreground">
          View analysis →
        </span>
      </div>
    </button>
  );
}