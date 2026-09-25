"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";

import {
  ConfidenceBar,
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
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useAgents, useCalendar, useSignals } from "@/hooks/use-api";
import { AGENTS } from "@/lib/constants";
import { directionTone, formatDateTime, formatNumber, formatPrice } from "@/lib/format";
import type { SignalRecord } from "@/lib/types";

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function TechnicalDetail({ signal }: { signal: SignalRecord }) {
  const indicators = asRecord(signal.payload.indicators);
  const levels = asRecord(signal.payload.key_levels);
  const rows: Array<[string, string]> = [
    ["RSI (14)", formatNumber(Number(indicators.rsi), 1)],
    ["MACD histogram", formatNumber(Number(indicators.macd_histogram), 3)],
    ["EMA cross", String(indicators.ema_cross ?? "—")],
    ["ADX", formatNumber(Number(indicators.adx), 1)],
    ["ATR", formatNumber(Number(indicators.atr), 2)],
    ["Support", formatPrice(Number(levels.support))],
    ["Resistance", formatPrice(Number(levels.resistance))],
  ];
  return (
    <Panel title="Indicator Snapshot" description="Latest technical reading">
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between gap-2">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="tabular">{value}</dd>
          </div>
        ))}
      </dl>
    </Panel>
  );
}

function NewsDetail({ signal }: { signal: SignalRecord }) {
  const calendar = useCalendar({ importance: "HIGH", limit: 8 });
  return (
    <>
      <Panel title="Sentiment & Impact" description="Latest news signal">
        <div className="space-y-3 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Event</span>
            <span className="font-medium">{String(signal.payload.event ?? "—")}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Sentiment</span>
            <TonePill label={signal.direction} tone={directionTone(signal.direction)} />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Impact</span>
            <Badge variant="outline">{String(signal.payload.impact ?? "—")}</Badge>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Alert</span>
            <Badge variant="outline">{String(signal.payload.alert ?? "NONE")}</Badge>
          </div>
        </div>
      </Panel>
      <Panel title="Upcoming High-Impact Events" description="Next releases">
        {calendar.data.length === 0 ? (
          <EmptyState>No high-impact events in the horizon.</EmptyState>
        ) : (
          <div className="space-y-2 text-xs">
            {calendar.data.slice(0, 6).map((event) => (
              <div key={event.id} className="flex items-center justify-between gap-2">
                <span className="truncate">
                  <span className="text-muted-foreground">{event.countryCode}</span> {event.name}
                </span>
                <span className="tabular shrink-0 text-muted-foreground">
                  {formatDateTime(event.time)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

function RiskDetail({ signal, vetoes }: { signal: SignalRecord; vetoes: SignalRecord[] }) {
  const checks = Array.isArray(signal.payload.checks) ? signal.payload.checks : [];
  return (
    <>
      <Panel title="Risk Assessment" description="Latest risk check run">
        <div className="space-y-2">
          {checks.map((raw, index) => {
            const check = asRecord(raw);
            const passed = Boolean(check.passed);
            return (
              <div key={`${String(check.name)}-${index}`} className="flex items-start gap-2 text-xs">
                <StatusDot tone={passed ? "bull" : "bear"} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="capitalize">{String(check.name ?? "").replace(/_/g, " ")}</span>
                    {!check.blocking ? (
                      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                        advisory
                      </span>
                    ) : null}
                  </div>
                  <div className="text-muted-foreground">{String(check.detail ?? "")}</div>
                </div>
              </div>
            );
          })}
        </div>
      </Panel>
      <Panel title="Veto History" description="Blocked trades">
        {vetoes.length === 0 ? (
          <EmptyState>No vetoes recorded. All proposals passed risk checks.</EmptyState>
        ) : (
          <div className="space-y-2 text-xs">
            {vetoes.map((veto) => (
              <div key={veto.id} className="flex items-center justify-between gap-2">
                <span className="truncate text-bear">{String(veto.payload.reasoning ?? "Veto")}</span>
                <span className="tabular shrink-0 text-muted-foreground">
                  {formatDateTime(veto.created_at)}
                </span>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </>
  );
}

function DecisionDetail({ signal }: { signal: SignalRecord }) {
  const components = [
    { label: "Technical", value: Number(signal.payload.technical_score ?? 0), weight: "0.45" },
    { label: "News", value: Number(signal.payload.news_score ?? 0), weight: "0.25" },
    { label: "Risk", value: Number(signal.payload.risk_score ?? 0), weight: "0.30" },
  ];
  return (
    <Panel title="Voting Breakdown" description="Weighted consensus">
      <div className="space-y-4">
        {components.map((component) => (
          <div key={component.label} className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted-foreground">
                {component.label} <span className="text-muted-foreground/60">x{component.weight}</span>
              </span>
              <span className="tabular">{component.value.toFixed(3)}</span>
            </div>
            <ConfidenceBar value={component.value} tone={directionTone(component.label)} />
          </div>
        ))}
        <div className="rounded-lg bg-muted/40 p-3 text-xs">
          <div className="text-muted-foreground">Reasoning</div>
          <p className="mt-1">{String(signal.payload.reasoning ?? "—")}</p>
        </div>
      </div>
    </Panel>
  );
}

export function AgentDetail() {
  const params = useParams<{ agent: string }>();
  const agentId = params.agent;
  const meta = AGENTS.find((agent) => agent.id === agentId);
  const agents = useAgents();
  const signals = useSignals({ agent: agentId, limit: 60 });
  const [enabled, setEnabled] = useState(true);

  const status = agents.data.find((agent) => agent.name === agentId);
  const latest = signals.data[0];

  const vetoes = useMemo(
    () => signals.data.filter((record) => record.kind === "risk_assessment" && record.direction === "VETO"),
    [signals.data],
  );

  if (!meta) {
    return (
      <div className="space-y-4">
        <Link href="/agents" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Back to agents
        </Link>
        <EmptyState>Unknown agent “{agentId}”.</EmptyState>
      </div>
    );
  }

  const tone = status?.status === "active" ? "bull" : status?.status === "error" ? "bear" : "flat";

  return (
    <div className="space-y-6">
      <Link href="/agents" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Back to agents
      </Link>

      <PageHeader
        title={
          <span className="flex items-center gap-3">
            <span className="relative size-9 shrink-0 overflow-hidden rounded-lg ring-1 ring-border">
              <Image src={meta.logo} alt={meta.name} fill sizes="36px" className="object-cover" priority />
            </span>
            {meta.name}
          </span>
        }
        description={meta.description}
        actions={
          <div className="flex items-center gap-3">
            <Badge variant="outline" className="capitalize">
              {status?.status ?? "idle"}
            </Badge>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch checked={enabled} onCheckedChange={setEnabled} />
              {enabled ? "Enabled" : "Disabled"}
            </div>
          </div>
        }
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Status"
          value={<span className="flex items-center gap-2 text-lg capitalize"><StatusDot tone={tone} pulse={status?.status === "active"} />{status?.status ?? "idle"}</span>}
          hint="Advisory toggle controls this UI only"
          icon={
            <span className="relative block size-4 overflow-hidden rounded ring-1 ring-border">
              <Image src={meta.logo} alt="" fill sizes="16px" className="object-cover" />
            </span>
          }
        />
        <StatCard label="Signals" value={status?.signal_count ?? 0} hint="Recorded" />
        <StatCard
          label="Avg Confidence"
          value={status ? `${(status.avg_confidence * 100).toFixed(0)}%` : "—"}
          hint="Across signals"
        />
        <StatCard
          label="Last Heartbeat"
          value={status?.last_signal_at ? formatDateTime(status.last_signal_at) : "—"}
          hint="Most recent signal"
        />
      </section>

      {agents.error ? <ErrorNote>{agents.error}</ErrorNote> : null}
      {signals.error ? <ErrorNote>{signals.error}</ErrorNote> : null}

      {latest ? (
        <Panel
          title="Latest Signal"
          description={`${latest.symbol} · ${formatDateTime(latest.created_at)}`}
          action={<TonePill label={latest.direction} tone={directionTone(latest.direction)} />}
        >
          <ConfidenceBar value={latest.confidence} tone={directionTone(latest.direction)} />
        </Panel>
      ) : (
        <EmptyState>No signals recorded for this agent yet.</EmptyState>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {latest && agentId === "technical_analyst" ? <TechnicalDetail signal={latest} /> : null}
        {latest && agentId === "news_monitor" ? <NewsDetail signal={latest} /> : null}
        {latest && agentId === "risk_manager" ? <RiskDetail signal={latest} vetoes={vetoes} /> : null}
        {latest && agentId === "decision_maker" ? <DecisionDetail signal={latest} /> : null}
      </div>

      <Panel title="Signal History" description="Most recent 20 signals">
        {signals.loading && signals.data.length === 0 ? (
          <LoadingRows rows={6} />
        ) : signals.data.length === 0 ? (
          <EmptyState>No history.</EmptyState>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Time</TableHead>
                <TableHead>Symbol</TableHead>
                <TableHead>Direction</TableHead>
                <TableHead className="text-right">Confidence</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {signals.data.slice(0, 20).map((record) => (
                <TableRow key={record.id}>
                  <TableCell className="tabular text-xs text-muted-foreground">
                    {formatDateTime(record.created_at)}
                  </TableCell>
                  <TableCell className="text-xs">{record.symbol}</TableCell>
                  <TableCell>
                    <TonePill label={record.direction} tone={directionTone(record.direction)} />
                  </TableCell>
                  <TableCell className="tabular text-right text-xs">
                    {(record.confidence * 100).toFixed(0)}%
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Panel>

      <Panel title="Agent Logs" description="Reasoning extracted from recent signals">
        {signals.data.length === 0 ? (
          <EmptyState>No logs.</EmptyState>
        ) : (
          <pre className="max-h-72 overflow-auto rounded-lg bg-black/40 p-3 text-[11px] leading-relaxed text-muted-foreground">
            {signals.data
              .slice(0, 15)
              .map(
                (record) =>
                  `${formatDateTime(record.created_at)}  ${record.symbol}  ${record.direction}  ${String(
                    record.payload.reasoning ?? "",
                  )}`,
              )
              .join("\n")}
          </pre>
        )}
      </Panel>

      <Button variant="outline" onClick={() => signals.reload()} className="gap-2">
        Refresh
      </Button>
    </div>
  );
}
