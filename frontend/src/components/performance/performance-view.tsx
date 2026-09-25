"use client";

import { Download } from "lucide-react";
import { cn } from "cn";

import {
  EmptyState,
  ErrorNote,
  LoadingRows,
  PageHeader,
  Panel,
  StatCard,
} from "@/components/shared/primitives";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usePerformance } from "@/hooks/use-api";
import { DECISIONS, agentName } from "@/lib/constants";

const BUCKET_LABELS = ["0–20%", "20–40%", "40–60%", "60–80%", "80–100%"];

function BarChart({ values, labels, color }: { values: number[]; labels: string[]; color: string }) {
  const max = Math.max(...values, 1);
  return (
    <div className="flex h-40 items-end gap-2">
      {values.map((value, index) => (
        <div key={labels[index]} className="flex flex-1 flex-col items-center gap-1">
          <div className="tabular text-[10px] text-muted-foreground">{value}</div>
          <div
            className="w-full rounded-t"
            style={{
              height: `${Math.max((value / max) * 120, 2)}px`,
              background: color,
              opacity: 0.85,
            }}
          />
          <div className="text-[10px] text-muted-foreground">{labels[index]}</div>
        </div>
      ))}
    </div>
  );
}

export function PerformanceView() {
  const performance = usePerformance();
  const stats = performance.data;

  if (performance.loading && !stats) {
    return (
      <div className="space-y-6">
        <PageHeader title="Performance & Analytics" description="Signal quality across agents and symbols." />
        <LoadingRows rows={8} />
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="space-y-6">
        <PageHeader title="Performance & Analytics" description="Signal quality across agents and symbols." />
        {performance.error ? <ErrorNote>{performance.error}</ErrorNote> : null}
        <EmptyState>No performance data yet. Run an analysis to populate analytics.</EmptyState>
      </div>
    );
  }

  const directionalTotal = stats.bullish + stats.bearish + stats.neutral || 1;
  const hourLabels = stats.activity_by_hour.map((_, index) => `${index}`);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Performance & Analytics"
        description="Signal distribution, confidence calibration and per-agent throughput."
        actions={
          <Button
            variant="outline"
            size="sm"
            className="gap-1.5"
            onClick={() => {
              const blob = new Blob([JSON.stringify(stats, null, 2)], { type: "application/json" });
              const url = URL.createObjectURL(blob);
              const anchor = document.createElement("a");
              anchor.href = url;
              anchor.download = "performance.json";
              anchor.click();
              URL.revokeObjectURL(url);
            }}
          >
            <Download className="size-3.5" />
            Export
          </Button>
        }
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Total Signals" value={stats.total_signals} hint="All agents" />
        <StatCard label="Bullish" value={stats.bullish} hint={`${((stats.bullish / directionalTotal) * 100).toFixed(0)}% of directional`} tone="bull" />
        <StatCard label="Bearish" value={stats.bearish} hint={`${((stats.bearish / directionalTotal) * 100).toFixed(0)}% of directional`} tone="bear" />
        <StatCard
          label="Avg Confidence"
          value={`${(stats.avg_confidence * 100).toFixed(0)}%`}
          hint="Across all signals"
        />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Signal Distribution" description="Directional split of technical and news signals">
          <div className="space-y-3">
            {[
              { label: "Bullish", value: stats.bullish, className: "bg-bull" },
              { label: "Bearish", value: stats.bearish, className: "bg-bear" },
              { label: "Neutral", value: stats.neutral, className: "bg-flat" },
            ].map((item) => (
              <div key={item.label} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">{item.label}</span>
                  <span className="tabular">{item.value}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className={cn("h-full rounded-full", item.className)}
                    style={{ width: `${(item.value / directionalTotal) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Confidence Calibration" description="Distribution of signal confidence">
          <BarChart values={stats.confidence_buckets} labels={BUCKET_LABELS} color="#eab308" />
        </Panel>
      </div>

      <Panel title="Activity by Hour (UTC)" description="When signals are generated">
        <BarChart values={stats.activity_by_hour} labels={hourLabels} color="#3b82f6" />
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Per-Symbol Performance" description="Breakdown by instrument">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Symbol</TableHead>
                <TableHead className="text-right">Signals</TableHead>
                <TableHead className="text-right">Bullish</TableHead>
                <TableHead className="text-right">Bearish</TableHead>
                <TableHead className="text-right">Avg Conf.</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(stats.by_symbol).map(([symbol, entry]) => (
                <TableRow key={symbol}>
                  <TableCell className="font-medium">{symbol}</TableCell>
                  <TableCell className="tabular text-right">{entry.count}</TableCell>
                  <TableCell className="tabular text-right text-bull">{entry.bullish}</TableCell>
                  <TableCell className="tabular text-right text-bear">{entry.bearish}</TableCell>
                  <TableCell className="tabular text-right">
                    {(entry.avg_confidence * 100).toFixed(0)}%
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Panel>

        <Panel title="Per-Agent Attribution" description="Throughput and confidence by agent">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Agent</TableHead>
                <TableHead className="text-right">Signals</TableHead>
                <TableHead className="text-right">Avg Conf.</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(stats.by_agent).map(([agent, entry]) => (
                <TableRow key={agent}>
                  <TableCell>{agentName(agent)}</TableCell>
                  <TableCell className="tabular text-right">{entry.count}</TableCell>
                  <TableCell className="tabular text-right">
                    {(entry.avg_confidence * 100).toFixed(0)}%
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Panel>
      </div>

      <Panel title="Decision Distribution" description="Final votes across all cycles">
        <div className="flex flex-wrap gap-3">
          {DECISIONS.map((decision) => (
            <div key={decision} className="flex items-center gap-2 rounded-lg border border-border px-3 py-2">
              <Badge variant="outline">{decision}</Badge>
              <span className="tabular text-sm">{stats.decisions[decision] ?? 0}</span>
            </div>
          ))}
        </div>
      </Panel>

      <p className="text-xs text-muted-foreground">
        Accuracy and win-rate require realised price outcomes; this build reports signal
        distribution and confidence calibration from recorded cycles. Connect a persistent
        outcome store to enable true accuracy metrics.
      </p>
    </div>
  );
}
