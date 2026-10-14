"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { cn } from "cn";

import { useMarketContext } from "@/components/symbol-provider";
import { SectionLabel } from "@/components/dashboard/intel-sections";
import { ErrorNote } from "@/components/shared/primitives";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { FlipButton, FlipToggle } from "@/components/ui/flip-button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAnalysis } from "@/hooks/use-analysis";
import { useDemoMode } from "@/hooks/use-demo-market";
import { TIMEFRAME_SOURCE } from "@/lib/constants";
import type { ChartTimeframe } from "@/lib/types";

/* ------------------------------------------------------------------ *
 * Options
 * ------------------------------------------------------------------ */

const ANALYSIS_TIMEFRAMES: Array<{ value: ChartTimeframe; label: string }> = [
  { value: "M5", label: "5M" },
  { value: "M15", label: "15M" },
  { value: "H1", label: "1H" },
  { value: "H4", label: "4H" },
  { value: "D1", label: "1D" },
];

const ANALYSIS_TYPES = [
  "Comprehensive Analysis",
  "Technical Analysis",
  "Market Structure",
  "Momentum Analysis",
  "Volume Analysis",
  "Sentiment Analysis",
] as const;

const AGENT_MODULES = [
  { key: "technical_analyst", label: "Technical Analyst" },
  { key: "market_structure", label: "Market Structure" },
  { key: "momentum_analyst", label: "Momentum Analyst" },
  { key: "news_sentiment", label: "News & Sentiment" },
  { key: "volume_analyst", label: "Volume Analyst" },
] as const;

const DEPTHS = {
  Quick: "Fast market overview",
  Standard: "Technical and market structure analysis",
  Deep: "Comprehensive multi-factor AI analysis",
} as const;

type AnalysisType = (typeof ANALYSIS_TYPES)[number];
type Depth = keyof typeof DEPTHS;
type AgentKey = (typeof AGENT_MODULES)[number]["key"];

/** Additional timeframes offered when multi-timeframe is enabled. */
const EXTRA_TIMEFRAMES: Array<{ value: ChartTimeframe; label: string }> = [
  { value: "M15", label: "15M" },
  { value: "H4", label: "4H" },
  { value: "D1", label: "1D" },
];

const INCLUDED = [
  "Market trend",
  "Momentum",
  "Technical indicators",
  "Market structure",
  "Volume",
  "Support & resistance",
  "Market sentiment",
  "Multi-timeframe context",
  "AI confidence",
  "Explanation / reasoning",
];

const STORAGE_KEY = "pkay.analysis-request";

interface AnalysisConfig {
  analysisType: AnalysisType;
  agents: AgentKey[];
  depth: Depth;
  multiTimeframe: boolean;
  extraTimeframes: ChartTimeframe[];
}

const DEFAULT_CONFIG: AnalysisConfig = {
  analysisType: "Comprehensive Analysis",
  agents: AGENT_MODULES.map((module) => module.key),
  depth: "Standard",
  multiTimeframe: false,
  extraTimeframes: ["M15", "H4", "D1"],
};

function loadConfig(): AnalysisConfig {
  if (typeof window === "undefined") return DEFAULT_CONFIG;
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (!stored) return DEFAULT_CONFIG;
    const parsed = JSON.parse(stored) as Partial<AnalysisConfig>;
    return {
      ...DEFAULT_CONFIG,
      ...parsed,
      agents:
        Array.isArray(parsed.agents) && parsed.agents.length
          ? parsed.agents
          : DEFAULT_CONFIG.agents,
    };
  } catch {
    return DEFAULT_CONFIG;
  }
}

/** BTCUSD → BTC/USD for display. */
function marketLabel(symbol: string): string {
  const value = symbol.toUpperCase();
  if (value.length === 6) return `${value.slice(0, 3)}/${value.slice(3)}`;
  return value;
}

function timeframeLabel(timeframe: ChartTimeframe): string {
  return ANALYSIS_TIMEFRAMES.find((item) => item.value === timeframe)?.label ?? timeframe;
}

/**
 * Generate AI Analysis panel.
 *
 * Configures an analytical run only: which market, which timeframe, which
 * analysis modules and how deep to go. It holds no money, sizing or execution
 * inputs — the platform analyses markets, it does not trade them.
 */
export function GenerateAnalysisDialog({
  open,
  onOpenChange,
  onGenerated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onGenerated: () => void;
}) {
  const { symbols, symbol, timeframe, setSymbol, setTimeframe } = useMarketContext();
  const demo = useDemoMode();
  const { loading, error, run } = useAnalysis();

  const [market, setMarket] = useState(symbol);
  const [selectedTimeframe, setSelectedTimeframe] = useState<ChartTimeframe>(timeframe);
  // Fresh values per open: the parent remounts this panel via `key`.
  const [config, setConfig] = useState<AnalysisConfig>(loadConfig);
  const [status, setStatus] = useState<"idle" | "done">("idle");

  const set = <K extends keyof AnalysisConfig>(key: K, value: AnalysisConfig[K]) =>
    setConfig((previous) => ({ ...previous, [key]: value }));

  const toggleAgent = (key: AgentKey) =>
    setConfig((previous) => ({
      ...previous,
      agents: previous.agents.includes(key)
        ? previous.agents.filter((item) => item !== key)
        : [...previous.agents, key],
    }));

  const allAgentsSelected = config.agents.length === AGENT_MODULES.length;

  const toggleExtraTimeframe = (value: ChartTimeframe) =>
    setConfig((previous) => ({
      ...previous,
      extraTimeframes: previous.extraTimeframes.includes(value)
        ? previous.extraTimeframes.filter((item) => item !== value)
        : [...previous.extraTimeframes, value],
    }));

  const submit = () => {
    if (demo || loading || config.agents.length === 0) return;
    void (async () => {
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
      } catch {
        /* storage is best-effort */
      }

      // The gateway accepts multiple intervals, so multi-timeframe runs are
      // requested for real rather than simulated.
      const requested = config.multiTimeframe
        ? [selectedTimeframe, ...config.extraTimeframes.filter((tf) => tf !== selectedTimeframe)]
        : [selectedTimeframe];

      setSymbol(market);
      setTimeframe(selectedTimeframe);
      await run(
        market,
        requested.map((tf) => TIMEFRAME_SOURCE[tf]),
      );

      onGenerated();
      setStatus("done");
      window.setTimeout(() => {
        setStatus("idle");
        onOpenChange(false);
      }, 900);
    })();
  };

  const busy = loading;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[88vh] w-full overflow-y-auto bg-card sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Generate AI Analysis</DialogTitle>
          <DialogDescription>
            Choose a market and timeframe to generate a fresh AI market analysis.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Market + timeframe */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Market</Label>
              <Select value={market} onValueChange={setMarket}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {symbols.map((item) => (
                    <SelectItem key={item} value={item}>
                      {marketLabel(item)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label>Timeframe</Label>
              <Select
                value={selectedTimeframe}
                onValueChange={(value) => setSelectedTimeframe(value as ChartTimeframe)}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ANALYSIS_TIMEFRAMES.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Analysis type */}
          <div className="space-y-1.5">
            <Label>Analysis Type</Label>
            <Select
              value={config.analysisType}
              onValueChange={(value) => set("analysisType", value as AnalysisType)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ANALYSIS_TYPES.map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Analysis agents */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Analysis Agents</Label>
              <button
                type="button"
                onClick={() =>
                  set("agents", allAgentsSelected ? [] : AGENT_MODULES.map((m) => m.key))
                }
                className="rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {allAgentsSelected ? "Clear all" : "Select All"}
              </button>
            </div>
            <div className="grid gap-1.5 sm:grid-cols-2">
              {AGENT_MODULES.map((module) => {
                const checked = config.agents.includes(module.key);
                return (
                  <label
                    key={module.key}
                    className={cn(
                      "flex cursor-pointer items-center gap-2 rounded-md border border-border px-2.5 py-2 transition-colors",
                      checked ? "bg-accent/40" : "hover:bg-accent/20",
                    )}
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() => toggleAgent(module.key)}
                    />
                    <span className={cn("text-xs", checked && "font-medium")}>
                      {module.label}
                    </span>
                  </label>
                );
              })}
            </div>
            {config.agents.length === 0 ? (
              <p className="text-[11px] text-muted-foreground">
                Select at least one analysis agent.
              </p>
            ) : null}
          </div>

          {/* Analysis depth */}
          <div className="space-y-1.5">
            <Label>Analysis Depth</Label>
            <Select
              value={config.depth}
              onValueChange={(value) => set("depth", value as Depth)}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(DEPTHS) as Depth[]).map((item) => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">{DEPTHS[config.depth]}</p>
          </div>

          {/* Multi-timeframe */}
          <div className="space-y-2 rounded-md border border-border px-3 py-2.5">
            <div className="flex items-center justify-between">
              <div>
                <Label className="text-xs">Multi-Timeframe Analysis</Label>
                <p className="text-[11px] text-muted-foreground">
                  Compare conditions across timeframes.
                </p>
              </div>
              <FlipToggle
                checked={config.multiTimeframe}
                onCheckedChange={(checked) => set("multiTimeframe", checked)}
                ariaLabel="Multi-timeframe analysis"
                className="w-20"
              />
            </div>

            {config.multiTimeframe ? (
              <div className="space-y-1.5 border-t border-border pt-2">
                <div className="text-[11px] text-muted-foreground">
                  Primary ·{" "}
                  <span className="font-medium text-foreground">
                    {timeframeLabel(selectedTimeframe)}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {EXTRA_TIMEFRAMES.filter((item) => item.value !== selectedTimeframe).map(
                    (item) => {
                      const checked = config.extraTimeframes.includes(item.value);
                      return (
                        <label
                          key={item.value}
                          className={cn(
                            "flex cursor-pointer items-center gap-1.5 rounded border border-border px-2 py-1 text-[11px] transition-colors",
                            checked ? "bg-accent/40" : "hover:bg-accent/20",
                          )}
                        >
                          <Checkbox
                            checked={checked}
                            onCheckedChange={() => toggleExtraTimeframe(item.value)}
                          />
                          {item.label}
                        </label>
                      );
                    },
                  )}
                </div>
              </div>
            ) : null}
          </div>

          {/* Informational */}
          <div className="space-y-1.5">
            <SectionLabel>AI analysis will include</SectionLabel>
            <ul className="grid grid-cols-2 gap-x-3 gap-y-1">
              {INCLUDED.map((item) => (
                <li key={item} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <Check className="size-3 shrink-0 text-bull" />
                  {item}
                </li>
              ))}
            </ul>
          </div>

          {error ? <ErrorNote>{error}</ErrorNote> : null}
          {demo ? (
            <p className="text-xs text-muted-foreground">
              Analysis is simulated in demo mode.
            </p>
          ) : null}

          <div className="border-t border-border pt-3">
            <FlipButton
              text1="Analysis Complete"
              text2={busy ? "Analyzing Market…" : "Generate AI Analysis"}
              onClick={submit}
              disabled={demo || busy || config.agents.length === 0}
              flipped={status === "done"}
              ariaLabel="Generate AI analysis"
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
