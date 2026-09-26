"use client";

import { TrendingUp } from "lucide-react";
import {
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
} from "@/components/ui/chart";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { agentName } from "@/lib/constants";
import {
  decimalsForPrice,
  directionTone,
  formatDateTime,
  formatPrice,
} from "@/lib/format";
import {
  signalDirectionSign,
  signalLevels,
  signalReference,
  signalSeriesPoints,
} from "@/lib/signal-model";
import type { SignalRecord } from "@/lib/types";

// ---------------------------------------------------------------------------
// Custom tooltip (mirrors the line-charts-9 reference card)
// ---------------------------------------------------------------------------

interface DetailTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: { label: string; value: number } }>;
  label?: string;
  format: (value: number) => string;
}

function DetailTooltip({ active, payload, label, format }: DetailTooltipProps) {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-popover p-3 shadow-lg">
      <div className="mb-1 text-sm text-muted-foreground">{label ?? data.label}</div>
      <div className="flex items-center gap-2">
        <div className="text-base font-bold">{format(data.value)}</div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail chart (styled after 21st.dev line-charts-9)
// ---------------------------------------------------------------------------

function SignalDetailChart({
  record,
  config,
  digits,
}: {
  record: SignalRecord;
  config: ChartConfig;
  digits: number;
}) {
  const data = signalSeriesPoints(record, 40);
  const levels = signalLevels(record);
  const sign = signalDirectionSign(record);
  const color = sign >= 0 ? "var(--bull)" : "var(--bear)";
  const tone = directionTone(record.direction);
  const format = (value: number) => formatPrice(value, digits);

  const high = Math.max(...data.map((point) => point.value));
  const low = Math.min(...data.map((point) => point.value));
  const start = data[0]?.value ?? 0;
  const end = data[data.length - 1]?.value ?? 0;
  const change = end !== start ? ((end - start) / start) * 100 : 0;

  const lineRefs = [
    { y: levels.entry, label: "Entry", color: "var(--foreground)" },
    { y: levels.sl, label: "SL", color: "var(--bear)" },
    { y: levels.tp1, label: "TP1", color: "var(--gold)" },
    { y: levels.tp2, label: "TP2", color: "var(--bull)" },
  ].filter((item) => item.y != null) as Array<{
    y: number;
    label: string;
    color: string;
  }>;

  return (
    <Card className="bg-card ring-border">
      <CardContent className="flex flex-col items-stretch gap-4 p-4 sm:p-5">
        {/* Header */}
        <div>
          <div className="mb-1 text-sm text-muted-foreground">{record.symbol} price path</div>
          <div className="flex flex-wrap items-baseline gap-1.5">
            <span className="text-2xl font-bold sm:text-3xl">{format(end)}</span>
            <span
              className={
                tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-muted-foreground"
              }
            >
              <TrendingUp className="mr-0.5 inline size-3.5" />
              {change >= 0 ? "+" : ""}
              {change.toFixed(2)}%
            </span>
            <span className="text-xs text-muted-foreground">Last 3.3h</span>
          </div>
        </div>

        {/* Stats row */}
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>
            High: <span className="font-medium text-bull">{format(high)}</span>
          </span>
          <span>
            Low: <span className="font-medium text-bear">{format(low)}</span>
          </span>
          <span>
            Range:{" "}
            <span className={`font-medium ${tone === "bull" ? "text-bull" : "text-bear"}`}>
              {format(high - low)}
            </span>
          </span>
        </div>

        {/* Chart */}
        <ChartContainer
          config={config}
          className="aspect-auto h-72 w-full [&_.recharts-curve.recharts-tooltip-cursor]:stroke-initial"
        >
          <ComposedChart data={data} margin={{ top: 16, right: 10, left: 5, bottom: 8 }}>
            <defs>
              <linearGradient id="signalArea" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.14} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
              <filter id="signalLineShadow" x="-100%" y="-100%" width="300%" height="300%">
                <feDropShadow
                  dx="0"
                  dy="4"
                  stdDeviation="9"
                  floodColor={sign >= 0 ? "rgba(34,197,94,0.45)" : "rgba(239,68,68,0.45)"}
                />
              </filter>
            </defs>

            <CartesianGrid
              strokeDasharray="4 8"
              stroke="var(--input)"
              strokeOpacity={1}
              horizontal
              vertical={false}
            />

            {lineRefs.map((item) => (
              <ReferenceLine
                key={item.label}
                y={item.y}
                stroke={item.color}
                strokeDasharray="4 4"
                strokeWidth={1}
                label={{
                  value: item.label,
                  position: "insideBottomRight",
                  fontSize: 10,
                  fill: item.color,
                }}
              />
            ))}

            <XAxis
              dataKey="label"
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickMargin={12}
              interval="preserveStartEnd"
              tickCount={5}
            />

            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              tickFormatter={(value) => format(Number(value))}
              tickMargin={12}
              domain={["auto", "auto"]}
              width={70}
            />

            <ChartTooltip
              content={<DetailTooltip format={format} />}
              cursor={{ strokeDasharray: "3 3", stroke: "var(--muted-foreground)", strokeOpacity: 0.5 }}
            />

            <Line
              type="monotone"
              dataKey="value"
              stroke={color}
              strokeWidth={2}
              filter="url(#signalLineShadow)"
              dot={false}
              activeDot={{ r: 5, fill: color, stroke: "var(--background)", strokeWidth: 2 }}
            />
          </ComposedChart>
        </ChartContainer>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Level row
// ---------------------------------------------------------------------------

function LevelRow({ label, value, toneClass }: { label: string; value: string; toneClass?: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border/60 py-2 last:border-b-0">
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={`tabular text-sm font-semibold ${toneClass ?? "text-foreground"}`}>{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Supported-levels helper
// ---------------------------------------------------------------------------

function supportingEntries(record: SignalRecord): Array<[string, string]> {
  const skip = new Set([
    "agent",
    "symbol",
    "decision",
    "direction",
    "final_score",
    "confidence",
    "entry_price",
    "stop_loss",
    "take_profit",
    "signal",
    "reasoning",
    "generated_at",
    "price",
    "key_levels",
    "approved",
  ]);
  return Object.entries(record.payload)
    .filter(
      ([key, value]) =>
        !skip.has(key) && value !== null && typeof value !== "object",
    )
    .map(([key, value]) => [key.replace(/_/g, " "), String(value)]);
}

// ---------------------------------------------------------------------------
// Detail dialog: chart left, rationale right
// ---------------------------------------------------------------------------

export function SignalDetailDialog({
  record,
  onOpenChange,
}: {
  record: SignalRecord | null;
  onOpenChange: (open: boolean) => void;
}) {
  const open = record !== null;
  const digits = record ? decimalsForPrice(signalReference(record)) : 2;
  const tone = record ? directionTone(record.direction) : "flat";
  const levels = record ? signalLevels(record) : null;
  const format = (value: number | null) =>
    value == null ? "—" : formatPrice(value, digits);
  const confidencePct = levels
    ? Math.round(Math.min(Math.max(levels.confidence, 0), 1) * 100)
    : 0;

  const config = {
    value: {
      label: "Price",
      color: tone === "bull" ? "var(--bull)" : tone === "bear" ? "var(--bear)" : "var(--flat)",
    },
  } satisfies ChartConfig;

  const reasoning =
    typeof record?.payload?.reasoning === "string" ? record.payload.reasoning : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl gap-0 overflow-hidden bg-popover p-0 sm:max-w-4xl">
        {record ? (
          <div className="grid lg:grid-cols-[1.1fr_1fr]">
            {/* Left: graph */}
            <div className="border-b border-border bg-card p-4 sm:p-5 lg:border-r lg:border-b-0">
              <SignalDetailChart record={record} config={config} digits={digits} />
            </div>

            {/* Right: rationale */}
            <div className="flex flex-col gap-4 p-4 sm:p-5">
              <DialogHeader className="gap-1">
                <DialogTitle className="flex flex-wrap items-center gap-2 text-base">
                  <Badge variant="outline" className="text-[10px]">
                    {record.symbol}
                  </Badge>
                  <span
                    className={
                      tone === "bull" ? "text-bull" : tone === "bear" ? "text-bear" : "text-muted-foreground"
                    }
                  >
                    {record.direction.toLowerCase()}
                  </span>
                </DialogTitle>
                <DialogDescription className="text-xs">
                  {agentName(record.agent)} · {record.kind.replace(/_/g, " ")} ·{" "}
                  {formatDateTime(record.created_at)}
                </DialogDescription>
              </DialogHeader>

              {/* Confidence */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="uppercase tracking-wider text-muted-foreground">Confidence</span>
                  <span className="tabular font-medium">{confidencePct}%</span>
                </div>
                <Progress
                  value={confidencePct}
                  className="h-2 bg-muted"
                  indicatorClassName={
                    tone === "bull" ? "bg-bull" : tone === "bear" ? "bg-bear" : "bg-flat"
                  }
                />
              </div>

              {/* Trade plan */}
              {levels ? (
                <div className="rounded-lg border border-border">
                  <div className="border-b border-border px-3 py-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
                    Trade plan
                  </div>
                  <div className="px-3">
                    <LevelRow label="Entry" value={format(levels.entry)} />
                    <LevelRow label="Stop Loss" value={format(levels.sl)} toneClass="text-bear" />
                    <LevelRow label="Target 1" value={format(levels.tp1)} toneClass="text-gold" />
                    <LevelRow label="Target 2" value={format(levels.tp2)} toneClass="text-bull" />
                  </div>
                </div>
              ) : null}

              {/* Rationale */}
              <div className="space-y-2">
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                  Rationale
                </div>
                <p className="text-sm leading-relaxed text-foreground/85">
                  {reasoning ?? "No textual rationale was recorded for this signal."}
                </p>
              </div>

              {/* Supporting details */}
              {levels ? (
                <div className="rounded-lg border border-border">
                  <div className="border-b border-border px-3 py-1.5 text-[11px] uppercase tracking-wider text-muted-foreground">
                    Supporting details
                  </div>
                  <div className="px-3">
                    {supportingEntries(record).map(([key, value]) => (
                      <div
                        key={key}
                        className="flex items-center justify-between gap-3 border-b border-border/60 py-2 last:border-b-0"
                      >
                        <span className="truncate text-xs capitalize text-muted-foreground">{key}</span>
                        <span className="tabular text-xs font-medium text-foreground">{value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}