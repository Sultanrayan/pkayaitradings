"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import type {
  CandlestickData,
  HistogramData,
  IChartApi,
  IPriceLine,
  ISeriesApi,
  LineData,
  SeriesMarker,
  Time,
  UTCTimestamp,
} from "lightweight-charts";

import { bollinger, ema } from "@/lib/indicators";
import { toUnixSeconds } from "@/lib/format";
import type { OhlcBar } from "@/lib/types";

export interface ChartOverlays {
  ema20: boolean;
  ema50: boolean;
  ema200: boolean;
  bollinger: boolean;
  volume: boolean;
}

export interface ChartMarker {
  time: number;
  position: "aboveBar" | "belowBar";
  color: string;
  shape: "arrowUp" | "arrowDown" | "circle";
  text: string;
}

export interface PriceChartHandle {
  screenshot: () => void;
  fitContent: () => void;
}

export interface PriceChartProps {
  bars: OhlcBar[];
  overlays: ChartOverlays;
  levels?: { support?: number | null; resistance?: number | null };
  markers?: ChartMarker[];
  height?: number;
}

function toLineData(times: UTCTimestamp[], values: (number | null)[]): LineData<Time>[] {
  const out: LineData<Time>[] = [];
  for (let i = 0; i < values.length; i += 1) {
    const value = values[i];
    if (value !== null && Number.isFinite(value)) out.push({ time: times[i], value });
  }
  return out;
}

export const PriceChart = forwardRef<PriceChartHandle, PriceChartProps>(function PriceChart(
  { bars, overlays, levels, markers = [], height = 420 },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const ema20Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema50Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const ema200Ref = useRef<ISeriesApi<"Line"> | null>(null);
  const bbUpperRef = useRef<ISeriesApi<"Line"> | null>(null);
  const bbLowerRef = useRef<ISeriesApi<"Line"> | null>(null);
  const markerRef = useRef<{ setMarkers: (markers: SeriesMarker<Time>[]) => void } | null>(null);
  const priceLinesRef = useRef<IPriceLine[]>([]);

  const series = useMemo(() => {
    const closes = bars.map((bar) => bar.close);
    return {
      candles: bars.map<CandlestickData<UTCTimestamp>>((bar) => ({
        time: toUnixSeconds(bar.openTime) as UTCTimestamp,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      })),
      volume: bars.map<HistogramData<UTCTimestamp>>((bar) => ({
        time: toUnixSeconds(bar.openTime) as UTCTimestamp,
        value: bar.tickVolume,
        color: bar.close >= bar.open ? "rgba(34,197,94,0.35)" : "rgba(239,68,68,0.35)",
      })),
      ema20: toLineData(
        bars.map((bar) => toUnixSeconds(bar.openTime) as UTCTimestamp),
        ema(closes, 20),
      ),
      ema50: toLineData(
        bars.map((bar) => toUnixSeconds(bar.openTime) as UTCTimestamp),
        ema(closes, 50),
      ),
      ema200: toLineData(
        bars.map((bar) => toUnixSeconds(bar.openTime) as UTCTimestamp),
        ema(closes, 200),
      ),
      bb: bollinger(closes, 20, 2),
    };
  }, [bars]);

  const timesRef = useRef<UTCTimestamp[]>(
    bars.map((bar) => toUnixSeconds(bar.openTime) as UTCTimestamp),
  );
  const dataRef = useRef(series);
  useEffect(() => {
    timesRef.current = bars.map((bar) => toUnixSeconds(bar.openTime) as UTCTimestamp);
    dataRef.current = series;
  });

  useImperativeHandle(ref, () => ({
    screenshot: () => {
      const chart = chartRef.current;
      if (!chart) return;
      const canvas = chart.takeScreenshot();
      const link = document.createElement("a");
      link.download = "pkay-chart.png";
      link.href = canvas.toDataURL("image/png");
      link.click();
    },
    fitContent: () => chartRef.current?.timeScale().fitContent(),
  }));

  useEffect(() => {
    let disposed = false;
    let resizeObserver: ResizeObserver | null = null;

    void (async () => {
      const { createChart, CandlestickSeries, HistogramSeries, LineSeries, ColorType, createSeriesMarkers } =
        await import("lightweight-charts");
      if (disposed || !containerRef.current) return;

      const chart = createChart(containerRef.current, {
        height,
        layout: {
          background: { type: ColorType.Solid, color: "transparent" },
          textColor: "#8b8b8b",
          fontFamily: "var(--font-geist-mono), monospace",
          attributionLogo: false,
        },
        grid: { vertLines: { color: "#101010" }, horzLines: { color: "#101010" } },
        rightPriceScale: { borderColor: "#1f1f1f" },
        timeScale: { borderColor: "#1f1f1f", timeVisible: true, secondsVisible: false },
        crosshair: {
          vertLine: { color: "#3f3f46", labelBackgroundColor: "#18181b" },
          horzLine: { color: "#3f3f46", labelBackgroundColor: "#18181b" },
        },
        localization: { locale: "en-US" },
      });

      const candle = chart.addSeries(CandlestickSeries, {
        upColor: "#22c55e",
        downColor: "#ef4444",
        borderVisible: false,
        wickUpColor: "#22c55e",
        wickDownColor: "#ef4444",
      });
      const volume = chart.addSeries(HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "",
      });
      volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });

      const ema20 = chart.addSeries(LineSeries, lineOptions("#eab308", 1));
      const ema50 = chart.addSeries(LineSeries, lineOptions("#3b82f6", 1));
      const ema200 = chart.addSeries(LineSeries, lineOptions("#a855f7", 1));
      const bbUpper = chart.addSeries(LineSeries, lineOptions("#52525b", 1));
      const bbLower = chart.addSeries(LineSeries, lineOptions("#52525b", 1));

      chartRef.current = chart;
      candleRef.current = candle;
      volumeRef.current = volume;
      ema20Ref.current = ema20;
      ema50Ref.current = ema50;
      ema200Ref.current = ema200;
      bbUpperRef.current = bbUpper;
      bbLowerRef.current = bbLower;
      markerRef.current = createSeriesMarkers(candle, []) as unknown as {
        setMarkers: (markers: SeriesMarker<Time>[]) => void;
      };

      const data = dataRef.current;
      candle.setData(data.candles);
      volume.setData(data.volume);
      ema20.setData(data.ema20);
      ema50.setData(data.ema50);
      ema200.setData(data.ema200);
      bbUpper.setData(toLineData(timesRef.current, data.bb.upper));
      bbLower.setData(toLineData(timesRef.current, data.bb.lower));
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
      candleRef.current = null;
      volumeRef.current = null;
      ema20Ref.current = null;
      ema50Ref.current = null;
      ema200Ref.current = null;
      bbUpperRef.current = null;
      bbLowerRef.current = null;
      markerRef.current = null;
      priceLinesRef.current = [];
    };
  }, [height]);

  useEffect(() => {
    const data = dataRef.current;
    candleRef.current?.setData(data.candles);
    volumeRef.current?.setData(data.volume);
    ema20Ref.current?.setData(data.ema20);
    ema50Ref.current?.setData(data.ema50);
    ema200Ref.current?.setData(data.ema200);
    bbUpperRef.current?.setData(toLineData(timesRef.current, data.bb.upper));
    bbLowerRef.current?.setData(toLineData(timesRef.current, data.bb.lower));
  }, [series]);

  useEffect(() => {
    ema20Ref.current?.applyOptions({ visible: overlays.ema20 });
    ema50Ref.current?.applyOptions({ visible: overlays.ema50 });
    ema200Ref.current?.applyOptions({ visible: overlays.ema200 });
    bbUpperRef.current?.applyOptions({ visible: overlays.bollinger });
    bbLowerRef.current?.applyOptions({ visible: overlays.bollinger });
    volumeRef.current?.applyOptions({ visible: overlays.volume });
  }, [overlays]);

  useEffect(() => {
    const candle = candleRef.current;
    if (!candle) return;
    for (const line of priceLinesRef.current) candle.removePriceLine(line);
    priceLinesRef.current = [];
    if (levels?.resistance) {
      priceLinesRef.current.push(
        candle.createPriceLine({
          price: levels.resistance,
          color: "#ef4444",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "R",
        }),
      );
    }
    if (levels?.support) {
      priceLinesRef.current.push(
        candle.createPriceLine({
          price: levels.support,
          color: "#22c55e",
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "S",
        }),
      );
    }
  }, [levels, series]);

  useEffect(() => {
    markerRef.current?.setMarkers(
      markers.map<SeriesMarker<Time>>((marker) => ({
        time: marker.time as UTCTimestamp,
        position: marker.position,
        color: marker.color,
        shape: marker.shape,
        text: marker.text,
      })),
    );
  }, [markers, series]);

  return <div ref={containerRef} className="w-full" />;
});

function lineOptions(color: string, width: 1 | 2 | 3 | 4) {
  return {
    color,
    lineWidth: width,
    priceLineVisible: false,
    lastValueVisible: false,
    crosshairMarkerVisible: false,
  } as const;
}
