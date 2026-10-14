"use client";

import { Info } from "lucide-react";
import { cn } from "cn";

import { ConfidenceBreakdown, IntelSection, LevelMeter, SectionLabel } from "@/components/dashboard/intel-sections";
import { EmptyState, LoadingRows } from "@/components/shared/primitives";
import { decimalsForPrice } from "@/lib/format";
import type { Bias, MarketIntel } from "@/lib/market-intel";

function biasText(bias: Bias): string {
  if (bias === "Bullish") return "text-bull";
  if (bias === "Bearish") return "text-bear";
  return "text-flat";
}

/**
 * AI Analysis — the dashboard's primary explanation surface.
 *
 * Answers "what is the AI view", "why" (derived reasons), "how confident"
 * (breakdown) and "which levels matter". The overall confidence prefers the
 * recorded signal confidence when one exists and falls back to the composite
 * market score.
 */
export function AiAnalysisPanel({
  intel,
  signalBias,
  signalConfidence,
  loading,
  reasoning,
}: {
  intel: MarketIntel;
  signalBias: Bias;
  signalConfidence: number | null;
  loading: boolean;
  reasoning: string | null;
}) {
  if (loading) {
    return (
      <IntelSection title="AI analysis" bodyClassName="p-3">
        <LoadingRows rows={4} />
      </IntelSection>
    );
  }

  if (!intel.ready) {
    return (
      <IntelSection title="AI analysis" bodyClassName="p-3">
        <EmptyState>The AI view appears once candles have loaded.</EmptyState>
      </IntelSection>
    );
  }

  const confidence = signalConfidence ?? intel.score;
  const digits = decimalsForPrice(intel.price ?? 1);

  return (
    <IntelSection
      title="AI analysis"
      hint={signalConfidence === null ? "Composite market read" : "From the latest signal"}
      bodyClassName="space-y-4"
    >
      {/* Headline */}
      <div>
        <div className={cn("text-3xl font-semibold leading-none tracking-tight", biasText(signalBias))}>
          {signalConfidence === null ? intel.structure.toUpperCase() : signalBias.toUpperCase()}
        </div>
        <div className="mt-1.5 flex items-center gap-2">
          <span className="tabular text-sm font-medium text-muted-foreground">
            {Math.round(confidence * 100)}% confidence
          </span>
          <span className="h-1 w-24 overflow-hidden rounded-full bg-muted">
            <span
              className={cn(
                "block h-full rounded-full",
                confidence >= 0.55 ? "bg-bull" : confidence <= 0.45 ? "bg-bear" : "bg-foreground",
              )}
              style={{ width: `${Math.round(confidence * 100)}%` }}
            />
          </span>
        </div>
      </div>

      {/* WHY */}
      <div>
        <SectionLabel>Why?</SectionLabel>
        <ul className="mt-1.5 space-y-1">
          {intel.reasons.map((reason) => (
            <li key={reason} className="flex gap-2 text-xs leading-relaxed text-muted-foreground">
              <span className="text-foreground/60">•</span>
              <span>{reason}</span>
            </li>
          ))}
        </ul>
        {reasoning ? (
          <p className="mt-2 flex gap-2 text-xs leading-relaxed text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0 text-muted-foreground/60" />
            <span>{reasoning}</span>
          </p>
        ) : null}
      </div>

      {/* KEY LEVELS */}
      <div>
        <SectionLabel>Key levels</SectionLabel>
        <div className="mt-1.5">
          <LevelMeter levels={intel.levels} digits={digits} />
        </div>
      </div>

      {/* CONFIDENCE BREAKDOWN */}
      <div>
        <SectionLabel>Confidence breakdown</SectionLabel>
        <div className="mt-1.5">
          <ConfidenceBreakdown parts={intel.breakdown} overall={confidence} />
        </div>
      </div>
    </IntelSection>
  );
}
