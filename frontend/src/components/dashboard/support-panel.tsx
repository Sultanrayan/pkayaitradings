"use client";

import { useState } from "react";
import { ChevronDown, Play, ShieldCheck, Wallet } from "lucide-react";
import { cn } from "cn";

import { DecisionPanel } from "@/components/dashboard/decision-panel";
import { NewsPanel } from "@/components/dashboard/news-panel";
import { PositionsPanel } from "@/components/dashboard/positions-panel";
import { RiskPanel } from "@/components/dashboard/risk-panel";
import { TechnicalPanel } from "@/components/dashboard/technical-panel";
import { ErrorNote } from "@/components/shared/primitives";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAnalysis } from "@/hooks/use-analysis";
import { MARKET_TIMEFRAMES, TIMEFRAME_SOURCE } from "@/lib/constants";
import type { ChartTimeframe } from "@/lib/types";

const PAIR_OPTIONS = ["XAUUSD", "BTCUSD"];

export function SupportPanel() {
  const { cycle, positions, equity, loading, error, run } = useAnalysis();
  const [pair, setPair] = useState(PAIR_OPTIONS[0]);
  const [timeframe, setTimeframe] = useState<ChartTimeframe>("H1");
  const [showRisk, setShowRisk] = useState(false);

  const activeTimeframe = MARKET_TIMEFRAMES.find((item) => item.value === timeframe);
  const timeframeLabel = activeTimeframe?.label ?? timeframe;

  const analyze = () => {
    void run(pair, [TIMEFRAME_SOURCE[timeframe]]);
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center overflow-hidden rounded-md border border-border">
          {PAIR_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setPair(option)}
              aria-pressed={pair === option}
              className={cn(
                "h-8 px-3 text-xs font-semibold transition-colors",
                pair === option ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50",
              )}
            >
              {option}
            </button>
          ))}
        </div>

        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => setShowRisk((value) => !value)}
          aria-expanded={showRisk}
        >
          {showRisk ? <ShieldCheck className="size-3.5" /> : <Wallet className="size-3.5" />}
          Balance & Risk Management
        </Button>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" className="gap-1.5">
              {timeframeLabel}
              <ChevronDown className="size-3.5 text-muted-foreground" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-28">
            <DropdownMenuLabel>Timeframe</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {MARKET_TIMEFRAMES.map((item) => {
              const activeItem = item.value === timeframe;
              return (
                <DropdownMenuItem
                  key={item.value}
                  onSelect={() => setTimeframe(item.value)}
                  className={activeItem ? "bg-accent font-medium" : undefined}
                >
                  <span className="flex w-full items-center justify-between gap-4">
                    {item.label}
                    {activeItem ? <span className="size-1.5 rounded-full bg-foreground" /> : null}
                  </span>
                </DropdownMenuItem>
              );
            })}
          </DropdownMenuContent>
        </DropdownMenu>

        <Button size="sm" className="gap-1.5" onClick={analyze} disabled={loading}>
          <Play className="size-3.5" />
          {loading ? "Analyzing…" : "Analysis Now"}
        </Button>
      </div>

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      {showRisk ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <PositionsPanel positions={positions} equity={equity} />
          <RiskPanel cycle={cycle} />
        </div>
      ) : null}

      {cycle ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <DecisionPanel cycle={cycle} />
          <TechnicalPanel cycle={cycle} />
          <NewsPanel cycle={cycle} />
          <RiskPanel cycle={cycle} />
        </div>
      ) : null}
    </div>
  );
}
