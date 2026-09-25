"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowRight, Bot } from "lucide-react";

import {
  EmptyState,
  ErrorNote,
  LoadingRows,
  PageHeader,
  Panel,
  StatCard,
  StatusDot,
} from "@/components/shared/primitives";
import { Badge } from "@/components/ui/badge";
import { useAgents, usePerformance } from "@/hooks/use-api";
import { AGENTS, agentName } from "@/lib/constants";
import { formatDateTime } from "@/lib/format";

export function AgentsView() {
  const agents = useAgents();
  const performance = usePerformance();

  const totalSignals = performance.data?.total_signals ?? 0;

  return (
    <div className="space-y-6">
      <PageHeader
        title="AI Agent Control Panel"
        description="Status, throughput and aggregate confidence for each specialised agent."
      />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Agents" value={AGENTS.length} hint="Technical · News · Risk · Decision" icon={<Bot className="size-4" />} />
        <StatCard
          label="Active"
          value={agents.data.filter((agent) => agent.status === "active").length}
          hint="Heartbeat within 15 minutes"
        />
        <StatCard label="Total Signals" value={totalSignals} hint="Across all agents" />
        <StatCard
          label="Avg Confidence"
          value={performance.data ? `${(performance.data.avg_confidence * 100).toFixed(0)}%` : "—"}
          hint="All recorded signals"
        />
      </section>

      {agents.error ? <ErrorNote>{agents.error}</ErrorNote> : null}

      <Panel title="Agent Fleet" description="Select an agent to open its control page">
        {agents.loading && agents.data.length === 0 ? (
          <LoadingRows rows={4} />
        ) : agents.data.length === 0 ? (
          <EmptyState>No agent activity recorded yet.</EmptyState>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {agents.data.map((agent) => {
              const meta = AGENTS.find((item) => item.id === agent.name);
              const tone = agent.status === "active" ? "bull" : agent.status === "error" ? "bear" : "flat";
              return (
                <Link
                  key={agent.name}
                  href={`/agents/${agent.name}`}
                  className="group flex flex-col gap-3 rounded-xl border border-border p-4 transition-colors hover:bg-accent/40"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex items-center gap-3">
                      <span
                        className="relative flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-lg ring-1 ring-border"
                        style={{ background: `${meta?.accent ?? "#71717a"}22` }}
                      >
                        {meta ? (
                          <Image
                            src={meta.logo}
                            alt={meta.name}
                            fill
                            sizes="40px"
                            className="object-cover"
                          />
                        ) : (
                          <Bot className="size-5 text-muted-foreground" />
                        )}
                      </span>
                      <div>
                        <div className="flex items-center gap-2 text-sm font-medium">
                          {agentName(agent.name)}
                          <StatusDot tone={tone} pulse={agent.status === "active"} />
                        </div>
                        <div className="text-xs text-muted-foreground">{meta?.role}</div>
                      </div>
                    </div>
                    <ArrowRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                  </div>

                  <p className="text-xs text-muted-foreground">{meta?.description}</p>

                  <div className="flex items-center justify-between border-t border-border pt-3 text-xs">
                    <span className="tabular">{agent.signal_count} signals</span>
                    <span className="tabular text-muted-foreground">
                      {(agent.avg_confidence * 100).toFixed(0)}% avg
                    </span>
                    <Badge variant="outline" className="capitalize">
                      {agent.status}
                    </Badge>
                  </div>

                  <div className="text-[11px] text-muted-foreground">
                    Last heartbeat: {agent.last_signal_at ? formatDateTime(agent.last_signal_at) : "—"}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </Panel>
    </div>
  );
}
