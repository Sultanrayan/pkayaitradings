"use client";

import { Panel, ConfidenceBar, EmptyState, TonePill } from "@/components/dashboard/ui-bits";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { directionTone, formatNumber, formatPrice } from "@/lib/format";
import type { CycleResponse } from "@/lib/types";

export function TechnicalPanel({ cycle }: { cycle: CycleResponse | null }) {
  if (!cycle) {
    return (
      <Panel title="Technical Analyst" description="Price action · indicators · ML ensemble">
        <EmptyState>No technical signal yet.</EmptyState>
      </Panel>
    );
  }

  const { technical } = cycle;
  const tone = directionTone(technical.signal);
  const indicators = technical.indicators;

  const rows: Array<[string, string]> = [
    ["RSI (14)", formatNumber(indicators.rsi, 1)],
    ["MACD hist", formatNumber(indicators.macd_histogram, 3)],
    ["EMA cross", indicators.ema_cross?.replace("_", " ") ?? "—"],
    ["ADX (14)", formatNumber(indicators.adx, 1)],
    ["ATR (14)", formatNumber(indicators.atr, 2)],
    ["BB upper", formatPrice(indicators.bb_upper)],
    ["BB lower", formatPrice(indicators.bb_lower)],
    ["MACD cross", indicators.macd_cross?.replace("_", " ") ?? "—"],
  ];

  return (
    <Panel
      title="Technical Analyst"
      description={`${technical.timeframe} · price action & indicators`}
      action={<TonePill label={technical.signal} tone={tone} />}
    >
      <div className="space-y-4">
        <ConfidenceBar value={technical.confidence} tone={tone} />

        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg bg-muted/40 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Support</div>
            <div className="tabular text-sm text-bull">{formatPrice(technical.key_levels.support)}</div>
          </div>
          <div className="rounded-lg bg-muted/40 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Resistance</div>
            <div className="tabular text-sm text-bear">{formatPrice(technical.key_levels.resistance)}</div>
          </div>
        </div>

        <Separator />

        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-xs">
          {rows.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between gap-2">
              <dt className="text-muted-foreground">{label}</dt>
              <dd className="tabular text-right">{value}</dd>
            </div>
          ))}
        </dl>

        <p className="text-xs leading-relaxed text-muted-foreground">{technical.reasoning}</p>

        <div className="flex flex-wrap gap-1.5">
          <Badge variant="outline" className="tabular font-normal">
            last {formatPrice(technical.price)}
          </Badge>
          <Badge variant="outline" className="font-normal">
            confidence {(technical.confidence * 100).toFixed(0)}%
          </Badge>
        </div>
      </div>
    </Panel>
  );
}
