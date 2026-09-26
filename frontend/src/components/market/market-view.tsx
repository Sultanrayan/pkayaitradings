"use client";

import * as React from "react";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Search, Star } from "lucide-react";
import { cn } from "cn";
import { Bar, BarChart, CartesianGrid, XAxis } from "recharts";

import { useMarketContext } from "@/components/symbol-provider";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart";
import { PageHeader } from "@/components/shared/primitives";
import { Input } from "@/components/ui/input";
import { useWatchlist } from "@/hooks/use-watchlist";
import { formatPrice, formatSignedPercent } from "@/lib/format";

/**
 * Market page: interactive bar-chart overview (Recharts) + asset list.
 * Selecting an asset opens its detailed chart view.
 */

type MetricKey = "price" | "change";

const METRICS: Record<MetricKey, { label: string }> = {
  price: { label: "Price" },
  change: { label: "Change" },
};

function toMetricRows(symbols: string[], ticks: Record<string, TickLike>) {
  return symbols.map((item) => {
    const tick = ticks[item];
    return {
      symbol: item,
      price: tick?.mid ?? 0,
      change: tick?.dayDiffPercent ?? 0,
    };
  });
}

export function MarketView() {
  const { symbols, symbol, setSymbol, ticks } = useMarketContext();
  const { symbols: watched, toggle } = useWatchlist();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [activeMetric, setActiveMetric] = useState<MetricKey>("change");

  const normalized = query.trim().toUpperCase();
  const assets = useMemo(
    () => (normalized ? symbols.filter((item) => item.includes(normalized)) : symbols),
    [symbols, normalized],
  );

  const rows = useMemo(() => toMetricRows(assets, ticks), [assets, ticks]);

  // Build chart payload so bars carry both price and change per asset.
  const chartData = useMemo(
    () =>
      rows.map((row) => ({
        symbol: row.symbol,
        price: row.price,
        change: Number(Number(row.change).toFixed(2)),
      })),
    [rows],
  );

  const total = useMemo(() => {
    const list = chartData.length ? chartData : [{ price: 0, change: 0 }];
    return {
      price: list.reduce((sum, row) => sum + row.price, 0) / list.length,
      change: list.reduce((sum, row) => sum + row.change, 0) / list.length,
    };
  }, [chartData]);

  const chartConfig = {
    price: {
      label: "Price",
      color: "var(--chart-1)",
    },
    change: {
      label: "Change",
      color: "var(--chart-2)",
    },
  } satisfies ChartConfig;

  const openAsset = (item: string) => {
    setSymbol(item);
    router.push("/dashboard");
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Market"
        description="Browse available markets, search for an asset and open its detailed chart."
      />

      <div className="relative max-w-md">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search assets…"
          className="pl-9"
        />
      </div>

      {/* Interactive chart card (Recharts) */}
      <Card className="py-0">
        <CardHeader className="flex flex-col items-stretch border-b !p-0 sm:flex-row">
          <div className="flex flex-1 flex-col justify-center gap-1 px-6 pt-4 pb-3 sm:py-0">
            <CardTitle>Market Overview</CardTitle>
            <CardDescription>Average price & day change across assets</CardDescription>
          </div>
          <div className="flex">
            {(Object.keys(METRICS) as MetricKey[]).map((key) => {
              const metric = METRICS[key];
              return (
                <button
                  key={key}
                  data-active={activeMetric === key}
                  className="relative z-30 flex flex-1 flex-col justify-center gap-1 border-t px-6 py-4 text-left text-muted-foreground data-[active=true]:bg-muted/50 even:border-l sm:border-t-0 sm:border-l sm:px-8 sm:py-6 sm:first:border-l-0"
                  onClick={() => setActiveMetric(key)}
                >
                  <span className="text-xs">{metric.label}</span>
                  <span className="text-lg font-bold leading-none tabular sm:text-3xl">
                    {key === "price"
                      ? formatPrice(total.price)
                      : formatSignedPercent(total.change)}
                  </span>
                </button>
              );
            })}
          </div>
        </CardHeader>
        <CardContent className="px-2 sm:p-6">
          <ChartContainer config={chartConfig} className="aspect-auto h-[250px] w-full">
            <BarChart
              accessibilityLayer
              data={chartData}
              margin={{ left: 12, right: 12 }}
              barCategoryGap="18%"
            >
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="symbol"
                tickLine={false}
                axisLine={false}
                tickMargin={8}
                minTickGap={32}
              />
              <ChartTooltip
                content={<ChartTooltipContent className="w-[170px]" />}
              />
              <Bar
                dataKey={activeMetric}
                fill={`var(--color-${activeMetric})`}
                radius={[6, 6, 0, 0]}
              />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>

      {/* Asset list */}
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {assets.map((item) => {
          const tick = ticks[item];
          const change = tick?.dayDiffPercent ?? null;
          const active = item === symbol;
          return (
            <div
              key={item}
              className={cn(
                "group rounded-xl border p-4 transition-colors",
                active ? "border-foreground/40 bg-card" : "border-border bg-card hover:border-foreground/25",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold">{item}</span>
                  <span className="truncate text-[11px] text-muted-foreground">
                    {tick?.description ?? ""}
                  </span>
                </div>
                <button
                  type="button"
                  aria-label={`Toggle ${item} favourite`}
                  onClick={() => toggle(item)}
                  className={cn(
                    "rounded p-1 text-muted-foreground transition-colors hover:bg-accent",
                    watched.includes(item) && "text-gold",
                  )}
                >
                  <Star className={cn("size-4", watched.includes(item) && "fill-gold")} />
                </button>
              </div>

              <div className="mt-3 flex items-end justify-between gap-2">
                <span className="tabular text-xl font-semibold">{formatPrice(tick?.mid)}</span>
                <span className={cn("tabular text-xs font-medium", change === null ? "text-muted-foreground" : change >= 0 ? "text-bull" : "text-bear")}>
                  {formatSignedPercent(change)}
                </span>
              </div>

              <div className="mt-4">
                <button
                  type="button"
                  onClick={() => openAsset(item)}
                  className="w-full rounded-lg border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-accent hover:text-foreground"
                >
                  Open chart
                </button>
              </div>
            </div>
          );
        })}
        {assets.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground sm:col-span-2 xl:col-span-3">
            No assets match “{query}”.
          </div>
        ) : null}
      </div>
    </div>
  );
}

interface TickLike {
  mid?: number;
  dayDiffPercent?: number | null;
}