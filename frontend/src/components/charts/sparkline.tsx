"use client";

import { useId } from "react";

export function Sparkline({
  values,
  color,
  height = 44,
  className,
}: {
  values: number[];
  color?: string;
  height?: number;
  className?: string;
}) {
  const gradientId = useId();
  if (values.length < 2) {
    return <div className={className} style={{ height }} />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 100;
  const step = width / (values.length - 1);
  const points = values.map((value, index) => {
    const x = index * step;
    const y = height - ((value - min) / span) * (height - 4) - 2;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const trendUp = values[values.length - 1] >= values[0];
  const stroke = color ?? (trendUp ? "#22c55e" : "#ef4444");
  const areaPath = `M0,${height} L${points.join(" L")} L${width},${height} Z`;

  return (
    <svg
      className={className}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      style={{ height, width: "100%" }}
      aria-hidden
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.35" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#${gradientId})`} />
      <polyline
        points={points.join(" ")}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}
