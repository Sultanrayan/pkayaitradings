"use client";

import { useMemo } from "react";
import { Sparkles } from "lucide-react";

import { BotPanel } from "@/components/bot/bot-panel";
import { PageHeader } from "@/components/shared/primitives";
import { useMarketContext } from "@/components/symbol-provider";
import { useSignals } from "@/hooks/use-api";

/** Dedicated AI assistant page using the same context-aware chat as the bot. */
export function AiView() {
  const { symbol, timeframe, activeTick } = useMarketContext();
  const signals = useSignals({ symbol, limit: 5 });

  const contextNote = useMemo(() => {
    const latest = signals.data[0];
    const parts = [`Viewing ${symbol} on ${timeframe}`];
    if (activeTick) parts.push(`last ${activeTick.mid.toFixed(4)}`);
    if (latest) parts.push(`latest signal: ${latest.direction} @ ${(latest.confidence * 100).toFixed(0)}%`);
    return parts.join(" — ");
  }, [symbol, timeframe, activeTick, signals.data]);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <PageHeader
        title={
          <span className="flex items-center gap-2">
            <Sparkles className="size-5 text-gold" /> AI Assistant
          </span>
        }
        description="A context-aware market assistant that knows the asset you are viewing."
      />

      <div className="rounded-xl border border-border bg-muted/40 px-4 py-2.5 text-xs text-muted-foreground">
        {contextNote}
      </div>

      <div className="flex-1">
        <BotPanel />
      </div>
    </div>
  );
}