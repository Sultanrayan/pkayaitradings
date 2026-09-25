"use client";

import { useMemo, useState } from "react";
import { Download, FileJson, Filter, Layers } from "lucide-react";
import { cn } from "cn";

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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { useSignals } from "@/hooks/use-api";
import { useNow } from "@/hooks/use-now";
import { AGENTS, DECISIONS, SIGNAL_DIRECTIONS, agentName } from "@/lib/constants";
import { directionTone, formatDateTime } from "@/lib/format";
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

function payloadEntries(record: SignalRecord): Array<[string, string]> {
  const skip = new Set(["agent", "symbol", "generated_at", "reasoning"]);
  return Object.entries(record.payload)
    .filter(([key, value]) => !skip.has(key) && value !== null && typeof value !== "object")
    .map(([key, value]) => [key, String(value)]);
}

export function SignalsView() {
  const { symbols } = useMarketContext();
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
  const now = useNow(30_000);

  const filtered = useMemo(() => {
    const range = TIME_RANGES.find((item) => item.value === timeRange);
    if (!range?.minutes) return signals.data;
    const cutoff = now - range.minutes * 60_000;
    return signals.data.filter((record) => new Date(record.created_at).getTime() >= cutoff);
  }, [signals.data, timeRange, now]);

  const latestCycle = useMemo(() => {
    if (!signals.data.length) return [];
    const correlationId = signals.data[0].correlation_id;
    return signals.data.filter((record) => record.correlation_id === correlationId);
  }, [signals.data]);

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
        description="Every agent signal with filtering, consensus and export."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() => download("signals.csv", toCsv(filtered), "text/csv")}
            >
              <Download className="size-3.5" />
              CSV
            </Button>
            <Button
              variant="outline"
              size="sm"
              className="gap-1.5"
              onClick={() =>
                download("signals.json", JSON.stringify(filtered, null, 2), "application/json")
              }
            >
              <FileJson className="size-3.5" />
              JSON
            </Button>
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
            <Label>Symbol</Label>
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
            <Label>Agent</Label>
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
            <Label>Direction</Label>
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
            <Label>Time range</Label>
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
            <Label>Minimum confidence — {(minConfidence * 100).toFixed(0)}%</Label>
            <Slider
              value={[minConfidence * 100]}
              max={100}
              step={5}
              onValueChange={(value) => setMinConfidence((value[0] ?? 0) / 100)}
            />
          </div>
        </div>
      </Panel>

      {signals.error ? <ErrorNote>{signals.error}</ErrorNote> : null}

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

      <Panel title="Signal Timeline" description="Newest first — click a row for detail">
        {signals.loading && signals.data.length === 0 ? (
          <LoadingRows rows={8} />
        ) : filtered.length === 0 ? (
          <EmptyState>No signals match the current filters.</EmptyState>
        ) : (
          <div className="divide-y divide-border">
            {filtered.map((record) => (
              <button
                key={record.id}
                type="button"
                onClick={() => setSelected(record)}
                className="flex w-full items-center gap-4 py-2.5 text-left transition-colors hover:bg-accent/30"
              >
                <span className="w-28 shrink-0 text-xs text-muted-foreground">
                  {formatDateTime(record.created_at)}
                </span>
                <Badge variant="outline" className="w-20 shrink-0 justify-center text-[10px]">
                  {record.symbol}
                </Badge>
                <span className="w-36 shrink-0 truncate text-sm">{agentName(record.agent)}</span>
                <TonePill label={record.direction} tone={directionTone(record.direction)} />
                <div className="ml-auto w-40">
                  <ConfidenceBar value={record.confidence} tone={directionTone(record.direction)} />
                </div>
              </button>
            ))}
          </div>
        )}
      </Panel>

      <Dialog open={selected !== null} onOpenChange={(open) => !open && setSelected(null)}>
        <DialogContent className="max-w-2xl bg-card">
          {selected ? (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-2">
                  {agentName(selected.agent)}
                  <TonePill label={selected.direction} tone={directionTone(selected.direction)} />
                </DialogTitle>
                <DialogDescription>
                  {selected.symbol} · {selected.kind.replace(/_/g, " ")} ·{" "}
                  {formatDateTime(selected.created_at)}
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4">
                <div className="space-y-1">
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                    Confidence
                  </div>
                  <ConfidenceBar value={selected.confidence} tone={directionTone(selected.direction)} />
                </div>

                {typeof selected.payload.reasoning === "string" ? (
                  <div className="space-y-1">
                    <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                      Supporting evidence
                    </div>
                    <p className="text-sm text-muted-foreground">{selected.payload.reasoning}</p>
                  </div>
                ) : null}

                <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                  {payloadEntries(selected).map(([key, value]) => (
                    <div key={key} className="flex items-center justify-between gap-2 text-xs">
                      <span className="capitalize text-muted-foreground">
                        {key.replace(/_/g, " ")}
                      </span>
                      <span className={cn("tabular text-right")}>{value}</span>
                    </div>
                  ))}
                </div>

                <details className="rounded-lg border border-border p-3">
                  <summary className="cursor-pointer text-xs text-muted-foreground">
                    Raw payload
                  </summary>
                  <pre className="mt-2 max-h-64 overflow-auto text-[11px] leading-relaxed text-muted-foreground">
                    {JSON.stringify(selected.payload, null, 2)}
                  </pre>
                </details>
              </div>
            </>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
