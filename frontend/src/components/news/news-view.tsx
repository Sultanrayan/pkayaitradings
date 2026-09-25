"use client";

import { useMemo, useState } from "react";
import { Clock, Newspaper, Search, TrendingDown, TrendingUp } from "lucide-react";
import { cn } from "cn";

import { EconomicCalendar, type EconomicEvent } from "@/components/economic-calendar";
import { useMarketContext } from "@/components/symbol-provider";
import {
  EmptyState,
  ErrorNote,
  LoadingRows,
  PageHeader,
  Panel,
  TonePill,
} from "@/components/shared/primitives";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCalendar, useNews, useSignals } from "@/hooks/use-api";
import { useNow } from "@/hooks/use-now";
import { directionTone, formatDateTime } from "@/lib/format";
import type { CalendarEvent, Impact } from "@/lib/types";

function useCountdown(target: string | null, now: number): string {
  if (!target) return "—";
  const delta = new Date(target).getTime() - now;
  if (delta <= 0) return "released";
  const totalSeconds = Math.floor(delta / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${hours}h ${minutes}m ${seconds}s`;
}

function SentimentGauge({ score, label }: { score: number; label: string }) {
  const position = Math.min(Math.max(score, 0), 1) * 100;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <TrendingDown className="size-3.5 text-bear" /> Bearish
        </span>
        <span className="tabular">{label}</span>
        <span className="flex items-center gap-1">
          Bullish <TrendingUp className="size-3.5 text-bull" />
        </span>
      </div>
      <div className="relative h-2 rounded-full bg-gradient-to-r from-bear via-flat to-bull">
        <div
          className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground"
          style={{ left: `${position}%` }}
        />
      </div>
    </div>
  );
}

function toEconomicEvents(events: CalendarEvent[]): EconomicEvent[] {
  return events.map((event) => ({
    countryCode: event.countryCode,
    time: new Date(event.time).toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }),
    eventName: event.name,
    actual: event.actual === null ? null : String(event.actual),
    forecast: event.forecast === null ? null : String(event.forecast),
    prior: event.previous === null ? null : String(event.previous),
    impact: event.importance.toLowerCase() as "high" | "medium" | "low",
  }));
}

export function NewsView() {
  const { symbol } = useMarketContext();
  const [importance, setImportance] = useState<Impact | "ALL">("HIGH");
  const [query, setQuery] = useState("");
  const news = useNews(symbol, 24);
  const calendar = useCalendar({
    importance: importance === "ALL" ? undefined : importance,
    limit: 60,
  });
  const newsSignals = useSignals({ symbol, agent: "news_monitor", limit: 1 });
  const now = useNow(1000);

  const latestNewsSignal = newsSignals.data[0];
  const sentimentScore =
    latestNewsSignal?.direction === "BULLISH"
      ? 0.5 + latestNewsSignal.confidence * 0.5
      : latestNewsSignal?.direction === "BEARISH"
        ? 0.5 - latestNewsSignal.confidence * 0.5
        : 0.5;

  const filteredNews = useMemo(() => {
    if (!query.trim()) return news.data;
    const needle = query.toLowerCase();
    return news.data.filter(
      (article) =>
        article.title.toLowerCase().includes(needle) ||
        (article.description ?? "").toLowerCase().includes(needle) ||
        article.publisher.toLowerCase().includes(needle),
    );
  }, [news.data, query]);

  const upcomingHigh = useMemo(
    () =>
      calendar.data
        .filter((event) => new Date(event.time).getTime() > now && event.importance === "HIGH")
        .sort((a, b) => new Date(a.time).getTime() - new Date(b.time).getTime()),
    [calendar.data, now],
  );

  const nextEvent = upcomingHigh[0] ?? null;
  const countdown = useCountdown(nextEvent?.time ?? null, now);

  return (
    <div className="space-y-6">
      <PageHeader
        title="News & Events"
        description={`Macro context for ${symbol} — headlines, sentiment and the economic calendar.`}
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title="Sentiment Gauge" description={`News Monitor view on ${symbol}`}>
          <div className="space-y-4">
            <SentimentGauge
              score={sentimentScore}
              label={latestNewsSignal ? latestNewsSignal.direction : "NEUTRAL"}
            />
            {latestNewsSignal ? (
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground">Event</span>
                <span className="font-medium">{String(latestNewsSignal.payload.event ?? "—")}</span>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                Run an analysis to populate the sentiment gauge.
              </p>
            )}
          </div>
        </Panel>

        <Panel title="High-Impact Countdown" description="Next scheduled release">
          {nextEvent ? (
            <div className="space-y-2">
              <div className="text-2xl font-semibold tabular text-gold">{countdown}</div>
              <div className="text-sm">{nextEvent.name}</div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Clock className="size-3.5" />
                {nextEvent.countryCode} · {formatDateTime(nextEvent.time)}
              </div>
            </div>
          ) : (
            <EmptyState>No upcoming high-impact events.</EmptyState>
          )}
        </Panel>

        <Panel title="Impact Mix" description="Scheduled releases by importance">
          <div className="space-y-2 text-sm">
            {(["HIGH", "MEDIUM", "LOW"] as const).map((level) => {
              const count = calendar.data.filter((event) => event.importance === level).length;
              return (
                <div key={level} className="flex items-center justify-between">
                  <Badge variant={level === "HIGH" ? "destructive" : "outline"} className="uppercase">
                    {level}
                  </Badge>
                  <span className="tabular">{count}</span>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>

      <Panel
        title={
          <span className="flex items-center gap-2">
            <Newspaper className="size-4" /> Live News Feed
          </span>
        }
        description={`${filteredNews.length} articles for ${symbol}`}
        action={
          <div className="relative w-48">
            <Search className="absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search news…"
              className="h-8 pl-7 text-xs"
            />
          </div>
        }
      >
        {news.error ? <ErrorNote>{news.error}</ErrorNote> : null}
        {news.loading && news.data.length === 0 ? (
          <LoadingRows rows={6} />
        ) : filteredNews.length === 0 ? (
          <EmptyState>No articles match your search.</EmptyState>
        ) : (
          <div className="divide-y divide-border">
            {filteredNews.map((article) => (
              <a
                key={article.url}
                href={article.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block py-3 transition-colors hover:bg-accent/30"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <div className="text-sm font-medium">{article.title}</div>
                    {article.description ? (
                      <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
                        {article.description}
                      </p>
                    ) : null}
                  </div>
                  <div className="shrink-0 text-right text-[11px] text-muted-foreground">
                    <div>{article.publisher || "News"}</div>
                    <div className="tabular">{formatDateTime(article.publishedDate)}</div>
                  </div>
                </div>
              </a>
            ))}
          </div>
        )}
      </Panel>

      <Panel
        title="Economic Calendar"
        description="Scheduled releases with actual / forecast / previous"
        action={
          <Select value={importance} onValueChange={(value) => setImportance(value as Impact | "ALL")}>
            <SelectTrigger className="h-8 w-32 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="ALL">All</SelectItem>
              <SelectItem value="HIGH">High</SelectItem>
              <SelectItem value="MEDIUM">Medium</SelectItem>
              <SelectItem value="LOW">Low</SelectItem>
            </SelectContent>
          </Select>
        }
      >
        {calendar.error ? <ErrorNote>{calendar.error}</ErrorNote> : null}
        {calendar.loading && calendar.data.length === 0 ? (
          <LoadingRows rows={4} />
        ) : calendar.data.length === 0 ? (
          <EmptyState>No events for this filter.</EmptyState>
        ) : (
          <EconomicCalendar title="Upcoming releases" events={toEconomicEvents(calendar.data)} />
        )}
      </Panel>

      {latestNewsSignal ? (
        <Panel title="Impact Classification" description="Latest news signal">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <TonePill
              label={latestNewsSignal.direction}
              tone={directionTone(latestNewsSignal.direction)}
            />
            <Badge variant="outline">{String(latestNewsSignal.payload.impact ?? "—")}</Badge>
            <span className={cn("text-xs text-muted-foreground")}>
              {String(latestNewsSignal.payload.reasoning ?? "")}
            </span>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
