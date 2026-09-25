"use client";

import { CalendarClock, Newspaper } from "lucide-react";
import { cn } from "cn";

import { Panel, EmptyState, TonePill } from "@/components/dashboard/ui-bits";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import type { Tone } from "@/lib/format";
import type { CycleResponse, Sentiment } from "@/lib/types";

function sentimentTone(sentiment: Sentiment): Tone {
  if (sentiment === "VERY_BULLISH" || sentiment === "BULLISH") return "bull";
  if (sentiment === "VERY_BEARISH" || sentiment === "BEARISH") return "bear";
  return "flat";
}

const ALERT_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  HALT_TRADING: "destructive",
  REDUCE_POSITION_SIZE: "secondary",
  MONITOR: "outline",
  NONE: "outline",
};

export function NewsPanel({ cycle }: { cycle: CycleResponse | null }) {
  if (!cycle) {
    return (
      <Panel title="News Monitor" description="Macro events · sentiment">
        <EmptyState>No news signal yet.</EmptyState>
      </Panel>
    );
  }

  const { news } = cycle;
  const tone = sentimentTone(news.sentiment);
  const alertVariant = ALERT_VARIANT[news.alert] ?? "outline";

  return (
    <Panel
      title="News Monitor"
      description="Macro calendar & headline sentiment"
      action={<TonePill label={news.sentiment.replace("_", " ")} tone={tone} />}
    >
      <div className="space-y-4">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-2">
            <Newspaper className="mt-0.5 size-4 text-muted-foreground" />
            <div>
              <div className="text-sm font-medium">{news.event.replace(/_/g, " ")}</div>
              <div className="text-xs text-muted-foreground">
                {news.affected_symbols.join(", ") || "—"}
              </div>
            </div>
          </div>
          <Badge
            variant={news.impact === "HIGH" ? "destructive" : "outline"}
            className={cn("uppercase", news.impact === "HIGH" && "bg-bear/20 text-bear")}
          >
            {news.impact}
          </Badge>
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="rounded-lg bg-muted/40 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Time to event
            </div>
            <div className="flex items-center gap-1.5">
              <CalendarClock className="size-3 text-muted-foreground" />
              <span className="tabular">{news.time_until_event ?? "—"}</span>
            </div>
          </div>
          <div className="rounded-lg bg-muted/40 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Alert</div>
            <Badge variant={alertVariant} className="mt-0.5 uppercase">
              {news.alert.replace(/_/g, " ")}
            </Badge>
          </div>
        </div>

        <Separator />

        <p className="text-xs leading-relaxed text-muted-foreground">{news.reasoning}</p>
      </div>
    </Panel>
  );
}
