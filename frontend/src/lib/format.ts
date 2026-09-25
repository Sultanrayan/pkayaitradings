/** Presentation helpers for prices, percentages and time. */

export function decimalsForPrice(price: number): number {
  const abs = Math.abs(price);
  if (abs >= 1000) return 2;
  if (abs >= 100) return 2;
  if (abs >= 1) return 4;
  return 5;
}

export function formatPrice(price: number | null | undefined, digits?: number): string {
  if (price === null || price === undefined || Number.isNaN(price)) return "—";
  const fractionDigits = digits ?? decimalsForPrice(price);
  return price.toLocaleString("en-US", {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  });
}

export function formatSignedPercent(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}%`;
}

export function formatSigned(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(digits)}`;
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return value.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function formatCompact(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(
    value,
  );
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("en-US", { hour12: false });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-US", { hour12: false });
}

export function formatQuoteAge(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  return `${Math.round(seconds / 3600)}h`;
}

/** Directional tone used for colour classes. */
export type Tone = "bull" | "bear" | "flat";

export function directionTone(direction: string): Tone {
  const value = direction.toUpperCase();
  if (value === "BULLISH" || value === "UP" || value === "BUY") return "bull";
  if (value === "BEARISH" || value === "DOWN" || value === "SELL") return "bear";
  return "flat";
}

export function scoreTone(score: number): Tone {
  if (score >= 0.55) return "bull";
  if (score <= 0.45) return "bear";
  return "flat";
}

export const toneTextClass: Record<Tone, string> = {
  bull: "text-bull",
  bear: "text-bear",
  flat: "text-flat",
};

export const toneBgClass: Record<Tone, string> = {
  bull: "bg-bull/10 text-bull ring-bull/30",
  bear: "bg-bear/10 text-bear ring-bear/30",
  flat: "bg-muted text-muted-foreground ring-border",
};

export function toUnixSeconds(iso: string): number {
  return Math.floor(new Date(iso).getTime() / 1000);
}
