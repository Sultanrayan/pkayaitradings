"use client";

import { useCallback, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  Activity,
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  Loader2,
  Minus,
  Newspaper,
  Play,
  TrendingDown,
  TrendingUp,
  Waves,
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "cn";

import { Sparkline } from "@/components/charts/sparkline";
import { useMarketContext } from "@/components/symbol-provider";
import {
  EmptyState,
  ErrorNote,
  LoadingRows,
  PageHeader,
  Panel,
  StatCard,
  StatusDot,
  TonePill,
} from "@/components/shared/primitives";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAgents, useAlerts, useNews, usePerformance, useSignals } from "@/hooks/use-api";
import { useAnalysis } from "@/hooks/use-analysis";
import { useOhlc } from "@/hooks/use-ohlc";
import { ANALYSIS_TIMEFRAMES, DECISIONS, agentMeta, agentName } from "@/lib/constants";
import {
  directionTone,
  formatDateTime,
  formatPrice,
  formatSignedPercent,
  scoreTone,
  toneTextClass,
} from "@/lib/format";
import type { AgentStatus, Alert, SignalRecord, Tick } from "@/lib/types";

function DirectionIcon({ direction }: { direction: string }) {
  const tone = directionTone(direction);
  if (tone === "bull") return <ArrowUpRight className="size-4 text-bull" />;
  if (tone === "bear") return <ArrowDownRight className="size-4 text-bear" />;
  return <Minus className="size-4 text-flat" />;
}

function MarketCard({
  symbol,
  tick,
  active,
  onSelect,
}: {
  symbol: string;
  tick?: Tick;
  active: boolean;
  onSelect: () => void;
}) {
  const { series } = useOhlc(symbol, "H1", 90);
  const closes = useMemo(() => series?.bars.map((bar) => bar.close) ?? [], [series]);
  const change = tick?.dayDiffPercent ?? null;
  const closed = tick?.marketState === "closed";

  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex flex-col gap-4 rounded-xl bg-card p-4 text-left ring-1 ring-border transition-colors hover:ring-foreground/25",
        active && "ring-foreground/40",
      )}
    >
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">{symbol}</span>
            {closed ? (
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                closed
              </span>
            ) : null}
          </div>
          <div className="mt-0.5 text-xs text-muted-foreground">
            {tick?.description ?? "Awaiting data…"}
          </div>
        </div>
        <DirectionIcon direction={tick?.direction ?? "FLAT"} />
      </div>

      <div className="flex items-end justify-between gap-4">
        <div className="tabular text-3xl font-semibold leading-none">{formatPrice(tick?.mid)}</div>
        <div
          className={cn(
            "tabular text-sm font-medium",
            change === null ? "text-muted-foreground" : change >= 0 ? "text-bull" : "text-bear",
          )}
        >
          {formatSignedPercent(change)}
        </div>
      </div>

      <Sparkline values={closes} />

      <div className="grid grid-cols-3 gap-2 border-t border-border pt-3 text-xs">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Bid</div>
          <div className="tabular">{formatPrice(tick?.bid)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Ask</div>
          <div className="tabular">{formatPrice(tick?.ask)}</div>
        </div>
        <div>
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Spread</div>
          <div className="tabular">{formatPrice(tick?.spread)}</div>
        </div>
      </div>
    </button>
  );
}

function AgentStatusRow({ agent }: { agent: AgentStatus }) {
  const tone = agent.status === "active" ? "bull" : agent.status === "error" ? "bear" : "flat";
  const meta = agentMeta(agent.name);
  return (
    <Link
      href={`/agents/${agent.name}`}
      className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 transition-colors hover:bg-accent/50"
    >
      <div className="flex items-center gap-2">
        <span className="relative size-8 shrink-0 overflow-hidden rounded-md ring-1 ring-border">
          {meta ? (
            <Image src={meta.logo} alt={meta.name} fill sizes="32px" className="object-cover" />
          ) : null}
        </span>
        <StatusDot tone={tone} pulse={agent.status === "active"} />
        <div>
          <div className="text-sm font-medium">{agentName(agent.name)}</div>
          <div className="text-[11px] text-muted-foreground">
            {agent.last_signal_at ? formatDateTime(agent.last_signal_at) : "No heartbeat"}
          </div>
        </div>
      </div>
      <div className="text-right text-xs">
        <div className="tabular">{agent.signal_count} signals</div>
        <div className="tabular text-muted-foreground">
          {(agent.avg_confidence * 100).toFixed(0)}% avg
        </div>
      </div>
    </Link>
  );
}

function SignalRow({ signal }: { signal: SignalRecord }) {
  const tone = directionTone(signal.direction);
  return (
    <Link
      href="/signals"
      className="flex items-center justify-between gap-3 border-b border-border py-2 text-sm last:border-0 hover:bg-accent/30"
    >
      <div className="flex min-w-0 items-center gap-2">
        <TonePill label={signal.direction} tone={tone} />
        <span className="truncate text-muted-foreground">{agentName(signal.agent)}</span>
      </div>
      <div className="flex items-center gap-3 text-xs">
        <span className="tabular text-muted-foreground">{(signal.confidence * 100).toFixed(0)}%</span>
        <span className="tabular text-muted-foreground">{formatDateTime(signal.created_at)}</span>
      </div>
    </Link>
  );
}

const PRIORITY_TONE: Record<string, "bull" | "bear" | "flat"> = {
  critical: "bear",
  high: "bear",
  medium: "flat",
  low: "flat",
};

function AlertRow({ alert }: { alert: Alert }) {
  return (
    <div className="flex items-start gap-2 border-b border-border py-2 text-xs last:border-0">
      <TonePill label={alert.priority} tone={PRIORITY_TONE[alert.priority] ?? "flat"} />
      <div className="min-w-0 flex-1">
        <div className="truncate font-medium">{alert.title}</div>
        <div className="truncate text-muted-foreground">{alert.detail}</div>
      </div>
      <span className="tabular shrink-0 text-muted-foreground">
        {formatDateTime(alert.created_at)}
      </span>
    </div>
  );
}

export function DashboardView() {
  const { symbols, symbol, ticks, setSymbol } = useMarketContext();
  const { cycle, loading, run } = useAnalysis();
  const performance = usePerformance();
  const agents = useAgents();
  const signals = useSignals({ limit: 40 });
  const alerts = useAlerts(6);
  const news = useNews(undefined, 12);
  const [newsFilter, setNewsFilter] = useState<string | null>(null);

  const stats = performance.data;

  const todaysSignals = useMemo(() => {
    const start = new Date();
    start.setHours(0, 0, 0, 0);
    return signals.data.filter((record) => new Date(record.created_at) >= start);
  }, [signals.data]);

  const handleRun = useCallback(async () => {
    const promise = run(symbol, ANALYSIS_TIMEFRAMES);
    toast.promise(promise, {
      loading: `Running ${symbol} analysis…`,
      success: "Analysis complete",
      error: "Analysis failed",
    });
    await promise;
  }, [run, symbol]);

  const tickerItems = newsFilter
    ? news.data.filter((article) => article.title.toLowerCase().includes(newsFilter.toLowerCase()))
    : news.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Market overview, agent status and the latest signals across XAUUSD and BTCUSD."
        actions={
          <Button onClick={handleRun} disabled={loading} className="gap-2">
            {loading ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
            Run analysis
            <span className="hidden text-xs opacity-70 sm:inline">
              {ANALYSIS_TIMEFRAMES.join(" · ")}
            </span>
          </Button>
        }
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Signals"
          value={stats?.total_signals ?? "—"}
          hint="Recorded across all agents"
          icon={<Activity className="size-4" />}
        />
        <StatCard
          label="Bullish"
          value={stats?.bullish ?? "—"}
          hint={`${stats?.neutral ?? 0} neutral`}
          icon={<TrendingUp className="size-4" />}
          tone="bull"
        />
        <StatCard
          label="Bearish"
          value={stats?.bearish ?? "—"}
          hint={`Avg confidence ${stats ? (stats.avg_confidence * 100).toFixed(0) : "—"}%`}
          icon={<TrendingDown className="size-4" />}
          tone="bear"
        />
        <StatCard
          label="Decisions"
          value={
            stats
              ? DECISIONS.reduce((acc, decision) => acc + (stats.decisions[decision] ?? 0), 0)
              : "—"
          }
          hint={
            stats
              ? `BUY ${stats.decisions.BUY ?? 0} · SELL ${stats.decisions.SELL ?? 0}`
              : "No cycles yet"
          }
          icon={<Waves className="size-4" />}
        />
      </section>

      {performance.error ? <ErrorNote>{performance.error}</ErrorNote> : null}

      <section className="grid gap-4 lg:grid-cols-2">
        {symbols.map((item) => (
          <MarketCard
            key={item}
            symbol={item}
            tick={ticks[item]}
            active={item === symbol}
            onSelect={() => setSymbol(item)}
          />
        ))}
      </section>

      <section className="grid gap-4 lg:grid-cols-3">
        <Panel title="Agent Status" description="Heartbeat and activity" className="lg:col-span-1">
          {agents.loading && agents.data.length === 0 ? (
            <LoadingRows rows={4} />
          ) : (
            <div className="space-y-2">
              {agents.data.map((agent) => (
                <AgentStatusRow key={agent.name} agent={agent} />
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Today's Signals"
          description={`${todaysSignals.length} recorded today`}
          action={
            <Link href="/signals" className="text-xs text-muted-foreground hover:text-foreground">
              View all
            </Link>
          }
        >
          {signals.loading && signals.data.length === 0 ? (
            <LoadingRows rows={5} />
          ) : signals.data.length === 0 ? (
            <EmptyState>No signals yet. Run an analysis to populate the feed.</EmptyState>
          ) : (
            <div className="max-h-72 overflow-y-auto pr-1">
              {signals.data.slice(0, 12).map((signal) => (
                <SignalRow key={signal.id} signal={signal} />
              ))}
            </div>
          )}
        </Panel>

        <Panel
          title="Recent Alerts"
          description="News, risk and execution events"
          action={
            <Link href="/alerts" className="text-xs text-muted-foreground hover:text-foreground">
              View all
            </Link>
          }
        >
          {alerts.data.length === 0 ? (
            <EmptyState>No alerts. The system is quiet.</EmptyState>
          ) : (
            <div>
              {alerts.data.map((alert) => (
                <AlertRow key={alert.id} alert={alert} />
              ))}
            </div>
          )}
        </Panel>
      </section>

      {cycle ? (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {[
            { label: "Technical", value: cycle.technical.signal, conf: cycle.technical.confidence },
            { label: "News", value: cycle.news.sentiment, conf: cycle.news.confidence },
            {
              label: "Risk",
              value: cycle.risk.approved ? "APPROVED" : "VETO",
              conf: cycle.risk.approved ? 1 : 0,
            },
            { label: "Decision", value: cycle.decision.decision, conf: cycle.decision.final_score },
          ].map((item) => (
            <Panel key={item.label} title={item.label} description="Latest cycle">
              <div className="flex items-center justify-between">
                <TonePill
                  label={item.value.replace("_", " ")}
                  tone={directionTone(item.value)}
                />
                <span className={cn("tabular text-sm", toneTextClass[scoreTone(item.conf)])}>
                  {(item.conf * 100).toFixed(0)}%
                </span>
              </div>
            </Panel>
          ))}
        </section>
      ) : null}

      <Panel
        title={
          <span className="flex items-center gap-2">
            <Newspaper className="size-4" /> News Ticker
          </span>
        }
        description="Latest market headlines — click a keyword to filter"
        action={
          <div className="flex items-center gap-2">
            <Badge variant="outline">{tickerItems.length} stories</Badge>
            {newsFilter ? (
              <button
                type="button"
                onClick={() => setNewsFilter(null)}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                clear
              </button>
            ) : null}
          </div>
        }
      >
        {news.loading && news.data.length === 0 ? (
          <LoadingRows rows={2} />
        ) : tickerItems.length === 0 ? (
          <EmptyState>No news available right now.</EmptyState>
        ) : (
          <div className="marquee-mask overflow-hidden">
            <div className="flex w-max animate-marquee gap-8">
              {[...tickerItems, ...tickerItems].map((article, index) => (
                <button
                  key={`${article.url}-${index}`}
                  type="button"
                  onClick={() => setNewsFilter(article.publisher || article.title.split(" ")[0])}
                  className="flex items-center gap-2 whitespace-nowrap text-sm text-muted-foreground hover:text-foreground"
                >
                  <span className="size-1.5 rounded-full bg-gold" />
                  <span className="font-medium text-foreground">{article.publisher || "News"}</span>
                  {article.title}
                </button>
              ))}
            </div>
          </div>
        )}
      </Panel>

      <Panel title="Agent Fleet" description="Specialised agents collaborating on every decision">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {agents.data.map((agent) => {
            const meta = agentMeta(agent.name);
            return (
              <Link
                key={agent.name}
                href={`/agents/${agent.name}`}
                className="flex items-center gap-3 rounded-lg border border-border p-3 transition-colors hover:bg-accent/40"
              >
                <div className="relative flex size-9 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-accent ring-1 ring-border">
                  {meta ? (
                    <Image
                      src={meta.logo}
                      alt={meta.name}
                      fill
                      sizes="36px"
                      className="object-cover"
                    />
                  ) : (
                    <Bot className="size-4" />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{agentName(agent.name)}</div>
                  <div className="text-[11px] capitalize text-muted-foreground">{agent.status}</div>
                </div>
              </Link>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
