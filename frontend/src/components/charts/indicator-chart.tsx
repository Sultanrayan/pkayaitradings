"use client";

import { useEffect, useMemo, useRef } from "react";
import type {
  HistogramData,
  IChartApi,
  ISeriesApi,
  LineData,
  UTCTimestamp,
} from "lightweight-charts";

import { toUnixSeconds } from "@/lib/format";
import type { OhlcBar } from "@/lib/types";

export interface IndicatorLine {
  label: string;
  color: string;
  values: (number | null)[];
}

export interface IndicatorChartProps {
  title: string;
  bars: OhlcBar[];
  lines: IndicatorLine[];
  histogram?: (number | null)[];
  references?: number[];
  height?: number;
}

function toLineData(times: UTCTimestamp[], values: (number | null)[]): LineData[] {
  const out: LineData[] = [];
  for (let i = 0; i < values.length; i += 1) {
    const value = values[i];
    if (value !== null && Number.isFinite(value)) out.push({ time: times[i], value });
  }
  return out;
}

export function IndicatorChart({
  title,
  bars,
  lines,
  histogram,
  references = [],
  height = 140,
}: IndicatorChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const lineRefs = useRef<ISeriesApi<"Line">[]>([]);
  const histogramRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const times = useMemo(
    () => bars.map((bar) => toUnixSeconds(bar.openTime) as UTCTimestamp),
    [bars],
  );
  const payload = useMemo(
    () => ({
      lines: lines.map((line) => ({ ...line, data: toLineData(times, line.values) })),
      histogram:
        histogram?.map<HistogramData>((value, i) => ({
          time: times[i],
          value: value ?? 0,
          color: (value ?? 0) >= 0 ? "rgba(34,197,94,0.5)" : "rgba(239,68,68,0.5)",
        })) ?? [],
    }),
    [lines, histogram, times],
  );
  const payloadRef = useRef(payload);
  const refsRef = useRef(references);
  useEffect(() => {
    payloadRef.current = payload;
    refsRef.current = references;
  });

  useEffect(() => {
    let disposed = false;
    let resizeObserver: ResizeObserver | null = null;

    void (async () => {
      const { createChart, LineSeries, HistogramSeries, ColorType } = await import(
        "lightweight-charts"
      );
      if (disposed || !containerRef.current) return;

      const chart = createChart(containerRef.current, {
        height,
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "#8b8b8b",
          fontFamily: "var(--font-geist-mono), monospace",
          attributionLogo: false,
        },
        grid: { vertLines: { color: "#0d0d0d" }, horzLines: { color: "#0d0d0d" } },
        rightPriceScale: { borderColor: "#1f1f1f" },
        timeScale: { borderColor: "#1f1f1f", timeVisible: true, secondsVisible: false },
        crosshair: {
          vertLine: { color: "#3f3f46", labelBackgroundColor: "#18181b" },
          horzLine: { color: "#3f3f46", labelBackgroundColor: "#18181b" },
        },
        localization: { locale: "en-US" },
      });

      if (payloadRef.current.histogram.length) {
        const hist = chart.addSeries(HistogramSeries, { priceLineVisible: false });
        hist.setData(payloadRef.current.histogram);
        histogramRef.current = hist;
      }

      lineRefs.current = payloadRef.current.lines.map((line) => {
        const series = chart.addSeries(LineSeries, {
          color: line.color,
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          crosshairMarkerVisible: false,
        });
        series.setData(line.data);
        return series;
      });

      for (const reference of refsRef.current) {
        const first = lineRefs.current[0];
        first?.createPriceLine({
          price: reference,
          color: "#27272a",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: false,
          title: "",
        });
      }

      chartRef.current = chart;
      chart.timeScale().fitContent();

      resizeObserver = new ResizeObserver((entries) => {
        const entry = entries[0];
        if (entry) chart.applyOptions({ width: entry.contentRect.width });
      });
      resizeObserver.observe(containerRef.current);
    })();

    return () => {
      disposed = true;
      resizeObserver?.disconnect();
      chartRef.current?.remove();
      chartRef.current = null;
      lineRefs.current = [];
      histogramRef.current = null;
    };
  }, [height]);

  useEffect(() => {
    lineRefs.current.forEach((series, index) => {
      series.setData(payload.lines[index]?.data ?? []);
    });
    histogramRef.current?.setData(payload.histogram);
  }, [payload]);

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-3 px-1 text-[11px] uppercase tracking-wider text-muted-foreground">
        <span>{title}</span>
        {lines.map((line) => (
          <span key={line.label} className="flex items-center gap-1 normal-case tracking-normal">
            <span className="inline-block size-2 rounded-full" style={{ background: line.color }} />
            {line.label}
          </span>
        ))}
      </div>
      <div ref={containerRef} className="w-full" />
    </div>
  );
}
