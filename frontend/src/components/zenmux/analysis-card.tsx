"use client";

import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { cn } from "cn";

import type { ZenmuxAnalysis, ZenmuxReasonSource } from "@/lib/api";

/**
 * Hairline border, matching the 21st Market Snapshot card's treatment.
 *
 * A fixed alpha over the foreground stays visible on both themes without needing a
 * separate token per side, which matters because this card is rendered on the card
 * surface inside the muted page background.
 */
const HAIRLINE = "color-mix(in srgb, var(--foreground) 8%, transparent)";

type Direction = ZenmuxAnalysis["direction"];

const DIRECTION_STYLE: Record<
  Direction,
  { label: string; text: string; bg: string; Icon: typeof ArrowUpRight }
> = {
  BULLISH: {
    label: "Bullish",
    text: "text-emerald-500",
    bg: "bg-emerald-500/10",
    Icon: ArrowUpRight,
  },
  BEARISH: {
    label: "Bearish",
    text: "text-rose-500",
    bg: "bg-rose-500/10",
    Icon: ArrowDownRight,
  },
  NEUTRAL: {
    label: "Neutral",
    text: "text-muted-foreground",
    bg: "bg-muted",
    Icon: Minus,
  },
};

/** Format a price with thousands separators and two decimals. */
function price(value: number): string {
  return value.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/** Format the upstream timestamp for the card footer, defensively. */
function stamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

/**
 * A short attribution label per source.
 *
 * The card shows which engine produced each part. Without this, a probability and
 * an EMA reading sit side by side looking like one model's output, which would
 * overstate what the classifier actually does.
 */
const SOURCE_LABEL: Record<ZenmuxReasonSource, string> = {
  analysis: "From price action",
  model: "From the model",
};

export interface AnalysisCardProps {
  analysis: ZenmuxAnalysis;
}

export function AnalysisCard({ analysis }: AnalysisCardProps) {
  const direction = DIRECTION_STYLE[analysis.direction];
  const { Icon } = direction;
  const confidence = Math.round(analysis.confidence * 100);

  return (
    <div
      className="w-full max-w-lg overflow-hidden rounded-xl border bg-card"
      style={{ borderColor: HAIRLINE }}
    >
      {/* Header: model, instrument, and the headline read. */}
      <div className="px-5 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-[11px] font-medium text-muted-foreground">
              {analysis.model_name}
            </p>
            <p className="mt-0.5 text-[11px] text-muted-foreground/70">
              {analysis.symbol_label} · {analysis.timeframe}
            </p>
          </div>          <div
            className={cn(
              "flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1",
              direction.bg,
              direction.text,
            )}
          >
            <Icon className="size-3.5" aria-hidden />
            <span className="text-[12px] font-semibold tracking-wide">{direction.label}</span>
          </div>
        </div>

        {/* Confidence and last close. */}
        <div className="mt-4 flex items-end justify-between gap-4">
          <div>
            <div className="flex items-baseline gap-1.5">
              <span
                className={cn(
                  "text-[26px] font-semibold leading-none tracking-tight tabular-nums",
                  direction.text,
                )}
              >
                {confidence}%
              </span>
              <span className="text-[12px] text-muted-foreground">
                Confidence
                {/* Only worth saying when the card's timeframe differs from the one
                    the classifier scored, since otherwise it is visible already. */}
                {analysis.model_timeframe !== analysis.timeframe ? (
                  <span className="whitespace-nowrap"> · {analysis.model_timeframe} basis</span>
                ) : null}
              </span>
            </div>
            {/* Confidence is reported as-is. Scaling it up to look decisive would
                misstate a |p-0.5|*2 value that sits near 0.1 on most bars. */}
            <div className="mt-2 h-1 w-32 overflow-hidden rounded-full bg-muted">
              <div
                className={cn("h-full rounded-full", direction.text.replace("text-", "bg-"))}
                style={{ width: `${Math.max(2, Math.min(100, confidence))}%` }}
              />
            </div>
          </div>
          <div className="text-right">
            <p className="text-[11px] text-muted-foreground">Last close</p>
            <p className="mt-0.5 text-[15px] font-medium tabular-nums">
              {price(analysis.close)}
            </p>
          </div>
        </div>
      </div>

      {/* Market structure. */}
      <div className="mt-5 px-5">
        <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          Market structure
        </p>
        {analysis.limited ? (
          <p className="mt-1.5 text-[13px] text-muted-foreground">
            Not enough closed bars yet to read structure.
          </p>
        ) : (
          <>
            <p className="mt-1.5 text-[14px] font-medium">{analysis.structure}</p>
            <p className="mt-0.5 text-[12.5px] text-muted-foreground">
              {analysis.structure_detail}
            </p>
          </>
        )}
      </div>

      {/* Why. */}
      {analysis.reasons.length > 0 ? (
        <div className="mt-5 px-5">
          <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
            Why
          </p>
          <ul className="mt-2 space-y-1.5">
            {analysis.reasons.map((reason, index) => (
              <li key={`${reason.source}-${index}`} className="flex items-start gap-2">
                <span className="mt-[7px] size-1 shrink-0 rounded-full bg-muted-foreground/60" />
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] leading-relaxed">{reason.detail}</span>
                  <span className="mt-0.5 block text-[10.5px] uppercase tracking-[0.06em] text-muted-foreground/60">
                    {SOURCE_LABEL[reason.source]}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Key levels. */}
      <div className="mt-5 px-5">
        <p className="text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground">
          Key levels
        </p>
        <div className="mt-2 grid grid-cols-2 gap-3">
          <div
            className="rounded-lg border px-3 py-2.5"
            style={{ borderColor: HAIRLINE }}
          >
            <p className="text-[10.5px] text-muted-foreground">Support</p>
            <p className="mt-0.5 text-[15px] font-medium tabular-nums text-emerald-500">
              {price(analysis.support)}
            </p>
          </div>
          <div
            className="rounded-lg border px-3 py-2.5"
            style={{ borderColor: HAIRLINE }}
          >
            <p className="text-[10.5px] text-muted-foreground">Resistance</p>
            <p className="mt-0.5 text-[15px] font-medium tabular-nums text-rose-500">
              {price(analysis.resistance)}
            </p>
          </div>
        </div>
      </div>

      {/* Footer. */}
      <div
        className="mt-5 flex items-center justify-between gap-3 border-t px-5 py-3"
        style={{ borderColor: HAIRLINE }}
      >
        <span className="text-[10.5px] text-muted-foreground">
          Updated {stamp(analysis.updated_at)}
        </span>
        {analysis.atr !== null ? (
          <span className="text-[10.5px] text-muted-foreground tabular-nums">
            Range {analysis.atr.toFixed(2)}
          </span>
        ) : null}
      </div>
    </div>
  );
}
