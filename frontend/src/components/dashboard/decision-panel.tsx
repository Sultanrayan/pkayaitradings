"use client";

import { CheckCircle2, ShieldAlert, ShieldCheck, XCircle } from "lucide-react";
import { cn } from "cn";

import { Panel, TonePill, EmptyState } from "@/components/dashboard/ui-bits";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { directionTone, formatPrice, scoreTone, toneTextClass } from "@/lib/format";
import type { CycleResponse } from "@/lib/types";

const DECISION_TONE = {
  BUY: "bull",
  SELL: "bear",
  WAIT: "flat",
  SKIP: "bear",
} as const;

function ScoreRow({ label, value, weight }: { label: string; value: number; weight: string }) {
  const tone = scoreTone(value);
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">
          {label} <span className="text-muted-foreground/60">{weight}</span>
        </span>
        <span className={cn("tabular font-medium", toneTextClass[tone])}>{value.toFixed(3)}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            tone === "bull" ? "bg-bull" : tone === "bear" ? "bg-bear" : "bg-foreground",
          )}
          style={{ width: `${Math.round(value * 100)}%` }}
        />
      </div>
    </div>
  );
}

export function DecisionPanel({ cycle }: { cycle: CycleResponse | null }) {
  if (!cycle) {
    return (
      <Panel title="Decision Maker" description="Weighted consensus vote">
        <EmptyState>Run an analysis to produce a trade decision.</EmptyState>
      </Panel>
    );
  }

  const { decision, risk, technical } = cycle;
  const tone = DECISION_TONE[decision.decision];
  const executed = decision.executed;

  return (
    <Panel
      title="Decision Maker"
      description="Technical x0.45 · News x0.25 · Risk x0.30"
      action={
        <Badge variant={executed ? "default" : "outline"} className="gap-1">
          {executed ? <CheckCircle2 className="size-3" /> : <XCircle className="size-3" />}
          {executed ? "EXECUTED" : "NOT EXECUTED"}
        </Badge>
      }
    >
      <div className="space-y-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className={cn("text-3xl font-semibold tracking-tight", toneTextClass[tone])}>
              {decision.decision}
            </span>
            <TonePill label={`${cycle.symbol} · ${technical.timeframe}`} tone={directionTone(technical.signal)} />
          </div>
          <div className="text-right">
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
              Final score
            </div>
            <div className={cn("tabular text-2xl font-semibold", toneTextClass[tone])}>
              {decision.final_score.toFixed(3)}
            </div>
          </div>
        </div>

        <div className="space-y-3">
          <ScoreRow label="Technical" value={decision.technical_score} weight="0.45" />
          <ScoreRow label="News" value={decision.news_score} weight="0.25" />
          <ScoreRow label="Risk" value={decision.risk_score} weight="0.30" />
        </div>

        <Separator />

        <div className="grid grid-cols-3 gap-3 text-xs">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Entry</div>
            <div className="tabular">{formatPrice(decision.entry_price)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Stop</div>
            <div className="tabular text-bear">{formatPrice(decision.stop_loss)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Target</div>
            <div className="tabular text-bull">{formatPrice(decision.take_profit)}</div>
          </div>
        </div>

        <div
          className={cn(
            "flex items-start gap-2 rounded-lg px-3 py-2 text-xs ring-1",
            risk.approved
              ? "bg-bull/5 text-bull ring-bull/20"
              : "bg-bear/5 text-bear ring-bear/20",
          )}
        >
          {risk.approved ? (
            <ShieldCheck className="mt-0.5 size-4 shrink-0" />
          ) : (
            <ShieldAlert className="mt-0.5 size-4 shrink-0" />
          )}
          <span>{risk.reasoning}</span>
        </div>

        <p className="text-xs leading-relaxed text-muted-foreground">{decision.reasoning}</p>
      </div>
    </Panel>
  );
}
