"use client";

import { useMemo } from "react";
import { Activity, AlertTriangle, Gauge, ShieldAlert } from "lucide-react";

import { useMarketContext } from "@/components/symbol-provider";
import {
  EmptyState,
  ErrorNote,
  LoadingRows,
  PageHeader,
  Panel,
  StatCard,
  StatusDot,
  TonePill,
} from "@/components/shared/primitives";
import { Badge } from "@/components/ui/badge";
import { useAlerts, useSignals } from "@/hooks/use-api";
import { useOhlc } from "@/hooks/use-ohlc";
import { agentName } from "@/lib/constants";
import { atr, ema, pearson, returns } from "@/lib/indicators";
import { directionTone, formatDateTime, formatNumber, formatPrice } from "@/lib/format";

const RISK_LIMITS = [
  { label: "Max drawdown", value: "5.00%", key: "MAX_DRAWDOWN_PCT" },
  { label: "Max position size", value: "50% of equity", key: "MAX_POSITION_SIZE" },
  { label: "VaR 95% limit", value: "2.00%", key: "VAR_LIMIT_PCT" },
  { label: "Correlation warn", value: "0.70", key: "CORRELATION_WARN_THRESHOLD" },
  { label: "Kelly fraction", value: "0.25", key: "KELLY_FRACTION" },
];

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function regimeFor(price: number, emaGap: number, atrPct: number): string {
  if (atrPct > 0.02) return "Volatile";
  if (Math.abs(emaGap) / (price || 1) > 0.01) return "Trending";
  return "Ranging";
}

export function RiskView() {
  const { symbols, symbol } = useMarketContext();
  const signals = useSignals({ agent: "risk_manager", limit: 60 });
  const alerts = useAlerts(50);
  const primary = useOhlc(symbol, "H1", 220);
  const secondarySymbol = symbols.find((item) => item !== symbol) ?? symbol;
  const secondary = useOhlc(secondarySymbol, "H1", 220);

  const latest = signals.data[0];
  const latestTechnical = useSignals({ symbol, agent: "technical_analyst", limit: 1 }).data[0];

  const marketStats = useMemo(() => {
    const bars = primary.series?.bars ?? [];
    if (bars.length < 30) return null;
    const closes = bars.map((bar) => bar.close);
    const atrValues = atr(bars, 14);
    const latestAtr = atrValues[atrValues.length - 1] ?? 0;
    const ema20 = ema(closes, 20).at(-1) ?? 0;
    const ema50 = ema(closes, 50).at(-1) ?? 0;
    const price = closes[closes.length - 1] ?? 0;
    const atrPct = price ? latestAtr / price : 0;
    const volatility = Math.sqrt(
      returns(closes)
        .slice(-60)
        .reduce((sum, value) => sum + value * value, 0) / 60,
    );
    return {
      price,
      atr: latestAtr,
      atrPct,
      emaGap: ema20 - ema50,
      regime: regimeFor(price, ema20 - ema50, atrPct),
      volatility,
    };
  }, [primary.series]);

  const correlation = useMemo(() => {
    const a = primary.series?.bars.map((bar) => bar.close) ?? [];
    const b = secondary.series?.bars.map((bar) => bar.close) ?? [];
    if (a.length < 10 || b.length < 10) return null;
    return pearson(returns(a), returns(b));
  }, [primary.series, secondary.series]);

  const vetoes = useMemo(
    () => signals.data.filter((record) => record.direction === "VETO"),
    [signals.data],
  );

  const riskAlerts = useMemo(
    () => alerts.data.filter((alert) => alert.type === "risk" || alert.priority === "critical"),
    [alerts.data],
  );

  const checks = latest ? (Array.isArray(latest.payload.checks) ? latest.payload.checks : []) : [];
  const varValue = latest ? Number(latest.payload.var_95 ?? NaN) : NaN;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Risk Analysis"
        description="Portfolio risk metrics, limit checks, market regime and correlation."
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="VaR 95% (1d)"
          value={Number.isFinite(varValue) ? `${(varValue * 100).toFixed(2)}%` : "—"}
          hint="On the proposed position"
          icon={<ShieldAlert className="size-4" />}
          tone={Number.isFinite(varValue) && varValue > 0.02 ? "bear" : "flat"}
        />
        <StatCard
          label="Volatility (60h)"
          value={marketStats ? `${(marketStats.volatility * 100).toFixed(2)}%` : "—"}
          hint="Realised hourly volatility"
          icon={<Activity className="size-4" />}
        />
        <StatCard
          label="Market Regime"
          value={marketStats?.regime ?? "—"}
          hint={`${symbol} · EMA20 vs EMA50`}
          icon={<Gauge className="size-4" />}
        />
        <StatCard
          label="Correlation"
          value={correlation === null ? "—" : correlation.toFixed(2)}
          hint={`${symbol} vs ${secondarySymbol}`}
          icon={<AlertTriangle className="size-4" />}
          tone={correlation !== null && Math.abs(correlation) > 0.7 ? "bear" : "flat"}
        />
      </section>

      {signals.error ? <ErrorNote>{signals.error}</ErrorNote> : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel
          title="Latest Risk Assessment"
          description={latest ? `${latest.symbol} · ${formatDateTime(latest.created_at)}` : "No assessment"}
          action={
            latest ? (
              <TonePill
                label={latest.direction}
                tone={latest.direction === "APPROVED" ? "bull" : "bear"}
              />
            ) : null
          }
        >
          {signals.loading && signals.data.length === 0 ? (
            <LoadingRows rows={5} />
          ) : checks.length === 0 ? (
            <EmptyState>Run an analysis to generate a risk assessment.</EmptyState>
          ) : (
            <div className="space-y-2">
              {checks.map((raw, index) => {
                const check = asRecord(raw);
                const passed = Boolean(check.passed);
                return (
                  <div key={`${String(check.name)}-${index}`} className="flex items-start gap-2 text-xs">
                    <span className="mt-0.5">
                      <StatusDot tone={passed ? "bull" : "bear"} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <span className="capitalize">
                          {String(check.name ?? "").replace(/_/g, " ")}
                        </span>
                        <span className="tabular text-muted-foreground">
                          {check.value === null || check.value === undefined
                            ? "—"
                            : formatNumber(Number(check.value), 4)}
                        </span>
                      </div>
                      <div className="text-muted-foreground">{String(check.detail ?? "")}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>

        <Panel title="Risk Limits" description="Configured via backend environment">
          <div className="space-y-2 text-xs">
            {RISK_LIMITS.map((limit) => (
              <div key={limit.key} className="flex items-center justify-between border-b border-border pb-2 last:border-0">
                <div>
                  <div>{limit.label}</div>
                  <div className="text-[10px] text-muted-foreground">{limit.key}</div>
                </div>
                <span className="tabular">{limit.value}</span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Volatility & ATR" description={`${symbol} · latest reading`}>
          {marketStats ? (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground">Price</div>
                <div className="tabular">{formatPrice(marketStats.price)}</div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground">ATR (14)</div>
                <div className="tabular">{formatNumber(marketStats.atr, 2)}</div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground">ATR %</div>
                <div className="tabular">{(marketStats.atrPct * 100).toFixed(2)}%</div>
              </div>
              <div>
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground">EMA gap</div>
                <div className="tabular">{formatNumber(marketStats.emaGap, 2)}</div>
              </div>
            </div>
          ) : (
            <EmptyState>Not enough candles to compute volatility.</EmptyState>
          )}
        </Panel>

        <Panel title="Veto History" description="Trades blocked by the Risk Manager">
          {vetoes.length === 0 ? (
            <EmptyState>No vetoes recorded.</EmptyState>
          ) : (
            <div className="space-y-2 text-xs">
              {vetoes.slice(0, 8).map((veto) => (
                <div key={veto.id} className="flex items-start justify-between gap-3 border-b border-border pb-2 last:border-0">
                  <span className="text-bear">{String(veto.payload.reasoning ?? "Veto")}</span>
                  <span className="tabular shrink-0 text-muted-foreground">
                    {formatDateTime(veto.created_at)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Risk Alerts Log" description="Critical and risk-derived notifications">
        {riskAlerts.length === 0 ? (
          <EmptyState>No risk alerts.</EmptyState>
        ) : (
          <div className="space-y-2 text-xs">
            {riskAlerts.slice(0, 10).map((alert) => (
              <div key={alert.id} className="flex items-start justify-between gap-3 border-b border-border pb-2 last:border-0">
                <div>
                  <div className="font-medium">{alert.title}</div>
                  <div className="text-muted-foreground">{alert.detail}</div>
                </div>
                <div className="shrink-0 text-right">
                  <Badge variant={alert.priority === "critical" ? "destructive" : "outline"}>
                    {alert.priority}
                  </Badge>
                  <div className="tabular mt-1 text-muted-foreground">
                    {formatDateTime(alert.created_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {latestTechnical ? (
        <Panel title="Signal Risk Attribution" description="Risk context for the latest technical signal">
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <TonePill
              label={latestTechnical.direction}
              tone={directionTone(latestTechnical.direction)}
            />
            <span className="text-muted-foreground">
              {agentName(latestTechnical.agent)} · confidence{" "}
              {(latestTechnical.confidence * 100).toFixed(0)}%
            </span>
            <span className="text-muted-foreground">
              {String(latestTechnical.payload.reasoning ?? "")}
            </span>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
