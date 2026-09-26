"use client";

import { useMemo, useState } from "react";
import { Download, FileJson, Filter, Layers } from "lucide-react";

import { useMarketContext } from "@/components/symbol-provider";
import {
  ConfidenceBar,
  EmptyState,
  ErrorNote,
  LoadingRows,
  PageHeader,
  Panel,
  TonePill,
} from "@/components/shared/primitives";
import { SignalCard } from "@/components/signals/signal-card";
import { SignalDetailDialog } from "@/components/signals/signal-detail";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { useDemoMode } from "@/hooks/use-demo-market";
import { useSignals } from "@/hooks/use-api";
import { useNow } from "@/hooks/use-now";
import { AGENTS, DECISIONS, SIGNAL_DIRECTIONS, agentName } from "@/lib/constants";
import { generateDemoSignalCards } from "@/lib/demo-data";
import { directionTone } from "@/lib/format";
import type { SignalRecord, SignalFilters } from "@/lib/types";

const TIME_RANGES = [
  { value: "all", label: "All time", minutes: null },
  { value: "15m", label: "Last 15m", minutes: 15 },
  { value: "1h", label: "Last 1h", minutes: 60 },
  { value: "24h", label: "Last 24h", minutes: 1440 },
] as const;

function download(filename: string, content: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function toCsv(records: SignalRecord[]): string {
  const header = ["id", "created_at", "symbol", "agent", "kind", "direction", "confidence"];
  const rows = records.map((record) =>
    [
      record.id,
      record.created_at,
      record.symbol,
      record.agent,
      record.kind,
      record.direction,
      record.confidence.toFixed(4),
    ].join(","),
  );
  return [header.join(","), ...rows].join("\n");
}

export function SignalsView() {
  const { symbols } = useMarketContext();
  const demo = useDemoMode();
  const [symbol, setSymbol] = useState<string>("all");
  const [agent, setAgent] = useState<string>("all");
  const [direction, setDirection] = useState<string>("all");
  const [minConfidence, setMinConfidence] = useState<number>(0);
  const [timeRange, setTimeRange] = useState<string>("all");
  const [selected, setSelected] = useState<SignalRecord | null>(null);

  const filters = useMemo<SignalFilters>(() => {
    const next: SignalFilters = { limit: 200 };
    if (symbol !== "all") next.symbol = symbol;
    if (agent !== "all") next.agent = agent;
    if (direction !== "all") next.direction = direction;
    if (minConfidence > 0) next.minConfidence = minConfidence;
    return next;
  }, [symbol, agent, direction, minConfidence]);

  const signals = useSignals(filters);
  const demoSignals = useMemo<SignalRecord[]>(
    () => (demo ? generateDemoSignalCards(symbols.length ? symbols : undefined, 8) : []),
    [demo, symbols],
  );

  const source = demo ? demoSignals : signals.data;
  const now = useNow(30_000);

  const filtered = useMemo(() => {
    const range = TIME_RANGES.find((item) => item.value === timeRange);
    if (!range?.minutes) return source;
    const cutoff = now - range.minutes * 60_000;
    return source.filter((record) => new Date(record.created_at).getTime() >= cutoff);
  }, [source, timeRange, now]);

  const latestCycle = useMemo(() => {
    if (!source.length) return [];
    const correlationId = source[0].correlation_id;
    return source.filter((record) => record.correlation_id === correlationId);
  }, [source]);

  const consensus = useMemo(() => {
    if (!latestCycle.length) return null;
    const technical = latestCycle.find((record) => record.agent === "technical_analyst");
    const news = latestCycle.find((record) => record.agent === "news_monitor");
    const risk = latestCycle.find((record) => record.agent === "risk_manager");
    const decision = latestCycle.find((record) => record.agent === "decision_maker");
    return { technical, news, risk, decision };
  }, [latestCycle]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Signals & Analysis Feed"
        description="Every agent signal as a card — 3 per row, open one for the full chart and rationale."
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => download("signals.csv", toCsv(filtered), "text/csv")}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-accent"
            >
              <Download className="size-3.5" />
              CSV
            </button>
            <button
              type="button"
              onClick={() =>
                download("signals.json", JSON.stringify(filtered, null, 2), "application/json")
              }
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-accent"
            >
              <FileJson className="size-3.5" />
              JSON
            </button>
          </div>
        }
      />

      <Panel
        title={
          <span className="flex items-center gap-2">
            <Filter className="size-4" /> Filters
          </span>
        }
        description={`${filtered.length} signals`}
      >
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Symbol</label>
            <Select value={symbol} onValueChange={setSymbol}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All symbols</SelectItem>
                {symbols.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Agent</label>
            <Select value={agent} onValueChange={setAgent}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All agents</SelectItem>
                {AGENTS.map((item) => (
                  <SelectItem key={item.id} value={item.id}>
                    {item.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Direction</label>
            <Select value={direction} onValueChange={setDirection}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Any direction</SelectItem>
                {[...SIGNAL_DIRECTIONS, ...DECISIONS, "APPROVED", "VETO"].map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Time range</label>
            <Select value={timeRange} onValueChange={setTimeRange}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIME_RANGES.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2 sm:col-span-2 lg:col-span-4">
            <label className="text-xs font-medium text-muted-foreground">
              Minimum confidence — {(minConfidence * 100).toFixed(0)}%
            </label>
            <Slider
              value={[minConfidence * 100]}
              max={100}
              step={5}
              onValueChange={(value) => setMinConfidence((value[0] ?? 0) / 100)}
            />
          </div>
        </div>
      </Panel>

      {!demo && signals.error ? <ErrorNote>{signals.error}</ErrorNote> : null}

      {consensus ? (
        <Panel
          title={
            <span className="flex items-center gap-2">
              <Layers className="size-4" /> Consensus — latest cycle
            </span>
          }
          description={`correlation ${latestCycle[0]?.correlation_id.slice(0, 10)}`}
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {[consensus.technical, consensus.news, consensus.risk, consensus.decision].map(
              (record) =>
                record ? (
                  <button
                    key={record.id}
                    type="button"
                    onClick={() => setSelected(record)}
                    className="space-y-2 rounded-lg border border-border p-3 text-left transition-colors hover:bg-accent/40"
                  >
                    <div className="text-xs text-muted-foreground">{agentName(record.agent)}</div>
                    <TonePill label={record.direction} tone={directionTone(record.direction)} />
                    <ConfidenceBar value={record.confidence} tone={directionTone(record.direction)} />
                  </button>
                ) : null,
            )}
          </div>
        </Panel>
      ) : null}

      {/* Card grid — one card per signal, 3 per row on xl screens */}
      {signals.loading && !demo && source.length === 0 ? (
        <LoadingRows rows={6} />
      ) : filtered.length === 0 ? (
        <EmptyState>No signals match the current filters.</EmptyState>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((record) => (
            <SignalCard key={record.id} record={record} onSelect={setSelected} />
          ))}
        </div>
      )}

      <SignalDetailDialog record={selected} onOpenChange={(open) => !open && setSelected(null)} />
    </div>
  );
}