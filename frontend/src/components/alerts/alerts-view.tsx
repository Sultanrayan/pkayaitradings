"use client";

import { useEffect, useMemo, useState } from "react";
import { Bell, BellRing, Plus, Trash2 } from "lucide-react";

import { useMarketContext } from "@/components/symbol-provider";
import {
  EmptyState,
  ErrorNote,
  LoadingRows,
  PageHeader,
  Panel,
  TonePill,
} from "@/components/shared/primitives";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { useAlerts } from "@/hooks/use-api";
import { AGENTS, SIGNAL_DIRECTIONS } from "@/lib/constants";
import { formatDateTime } from "@/lib/format";
import type { AlertPriority } from "@/lib/types";

interface AlertRule {
  id: string;
  symbol: string;
  agent: string;
  direction: string;
  minConfidence: number;
  enabled: boolean;
}

const STORAGE_KEY = "pkay.alertRules";

const PRIORITY_TONE: Record<AlertPriority, "bull" | "bear" | "flat"> = {
  critical: "bear",
  high: "bear",
  medium: "flat",
  low: "flat",
};

export function AlertsView() {
  const { symbols, symbol } = useMarketContext();
  const alerts = useAlerts(100);
  const [priority, setPriority] = useState<string>("all");
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [draft, setDraft] = useState<Omit<AlertRule, "id" | "enabled">>({
    symbol,
    agent: "technical_analyst",
    direction: "BULLISH",
    minConfidence: 0.7,
  });

  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let active = true;
    void (async () => {
      await Promise.resolve();
      if (!active) return;
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) {
        try {
          setRules(JSON.parse(stored) as AlertRule[]);
        } catch {
          /* ignore malformed storage */
        }
      }
      setLoaded(true);
    })();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!loaded) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rules));
  }, [rules, loaded]);

  const filtered = useMemo(
    () => (priority === "all" ? alerts.data : alerts.data.filter((alert) => alert.priority === priority)),
    [alerts.data, priority],
  );

  const addRule = () => {
    setRules((previous) => [
      ...previous,
      { ...draft, id: crypto.randomUUID(), enabled: true },
    ]);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Alerts & Notifications"
        description="Event history derived from signals, plus rule definitions."
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel
          title={
            <span className="flex items-center gap-2">
              <Plus className="size-4" /> Alert Builder
            </span>
          }
          description="Define conditions (in-app evaluation)"
          className="lg:col-span-1"
        >
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Symbol</Label>
              <Select
                value={draft.symbol}
                onValueChange={(value) => setDraft((prev) => ({ ...prev, symbol: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {symbols.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Agent</Label>
              <Select
                value={draft.agent}
                onValueChange={(value) => setDraft((prev) => ({ ...prev, agent: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AGENTS.map((item) => (
                    <SelectItem key={item.id} value={item.id}>
                      {item.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Direction</Label>
              <Select
                value={draft.direction}
                onValueChange={(value) => setDraft((prev) => ({ ...prev, direction: value }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SIGNAL_DIRECTIONS.map((item) => (
                    <SelectItem key={item} value={item}>
                      {item}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Confidence ≥ {(draft.minConfidence * 100).toFixed(0)}%</Label>
              <Slider
                value={[draft.minConfidence * 100]}
                max={100}
                step={5}
                onValueChange={(value) =>
                  setDraft((prev) => ({ ...prev, minConfidence: (value[0] ?? 0) / 100 }))
                }
              />
            </div>

            <Button onClick={addRule} className="w-full gap-2">
              <Plus className="size-4" /> Create alert rule
            </Button>

            <p className="text-[11px] text-muted-foreground">
              Rules are stored locally. Delivery channels (email, Telegram, push) require
              backend notification workers.
            </p>
          </div>
        </Panel>

        <Panel title="Active Rules" description={`${rules.length} configured`} className="lg:col-span-2">
          {rules.length === 0 ? (
            <EmptyState>No alert rules yet. Create one on the left.</EmptyState>
          ) : (
            <div className="space-y-2">
              {rules.map((rule) => (
                <div
                  key={rule.id}
                  className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant="outline">{rule.symbol}</Badge>
                    <span>{rule.agent.replace(/_/g, " ")}</span>
                    <TonePill
                      label={rule.direction}
                      tone={rule.direction === "BULLISH" ? "bull" : rule.direction === "BEARISH" ? "bear" : "flat"}
                    />
                    <span className="tabular text-muted-foreground">
                      ≥ {(rule.minConfidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    <Switch
                      checked={rule.enabled}
                      onCheckedChange={(checked) =>
                        setRules((previous) =>
                          previous.map((item) =>
                            item.id === rule.id ? { ...item, enabled: checked } : item,
                          ),
                        )
                      }
                    />
                    <button
                      type="button"
                      onClick={() => setRules((previous) => previous.filter((item) => item.id !== rule.id))}
                      className="text-muted-foreground hover:text-bear"
                      aria-label="Delete rule"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel
        title={
          <span className="flex items-center gap-2">
            <BellRing className="size-4" /> Alert History
          </span>
        }
        description={`${filtered.length} events`}
        action={
          <Select value={priority} onValueChange={setPriority}>
            <SelectTrigger className="h-8 w-32 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All</SelectItem>
              <SelectItem value="critical">Critical</SelectItem>
              <SelectItem value="high">High</SelectItem>
              <SelectItem value="medium">Medium</SelectItem>
              <SelectItem value="low">Low</SelectItem>
            </SelectContent>
          </Select>
        }
      >
        {alerts.error ? <ErrorNote>{alerts.error}</ErrorNote> : null}
        {alerts.loading && alerts.data.length === 0 ? (
          <LoadingRows rows={5} />
        ) : filtered.length === 0 ? (
          <EmptyState>
            <span className="flex items-center gap-2">
              <Bell className="size-4" /> No alerts recorded.
            </span>
          </EmptyState>
        ) : (
          <div className="divide-y divide-border">
            {filtered.map((alert) => (
              <div key={alert.id} className="flex items-start gap-3 py-3">
                <TonePill label={alert.priority} tone={PRIORITY_TONE[alert.priority]} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    {alert.title}
                    <Badge variant="outline" className="text-[10px]">
                      {alert.symbol}
                    </Badge>
                  </div>
                  <div className="text-xs text-muted-foreground">{alert.detail}</div>
                </div>
                <div className="shrink-0 text-right text-[11px] text-muted-foreground">
                  <div className="capitalize">{alert.type}</div>
                  <div className="tabular">{formatDateTime(alert.created_at)}</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
