"use client";

import { Check, Minus, ShieldAlert, ShieldCheck, X } from "lucide-react";
import { cn } from "cn";

import { Panel, EmptyState } from "@/components/dashboard/ui-bits";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { formatNumber, formatPrice } from "@/lib/format";
import type { CycleResponse } from "@/lib/types";

function CheckIcon({ passed, blocking }: { passed: boolean; blocking: boolean }) {
  if (passed) return <Check className="size-3.5 text-bull" />;
  if (blocking) return <X className="size-3.5 text-bear" />;
  return <Minus className="size-3.5 text-flat" />;
}

export function RiskPanel({ cycle }: { cycle: CycleResponse | null }) {
  if (!cycle) {
    return (
      <Panel title="Risk Manager" description="VaR · position sizing · veto">
        <EmptyState>No risk assessment yet.</EmptyState>
      </Panel>
    );
  }

  const { risk } = cycle;

  return (
    <Panel
      title="Risk Manager"
      description="Pre-trade checks · veto authority"
      action={
        <Badge
          variant={risk.approved ? "default" : "destructive"}
          className={cn("gap-1", risk.approved && "bg-bull/15 text-bull")}
        >
          {risk.approved ? <ShieldCheck className="size-3" /> : <ShieldAlert className="size-3" />}
          {risk.approved ? "APPROVED" : "VETO"}
        </Badge>
      }
    >
      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-3 text-xs">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Size</div>
            <div className="tabular">{formatNumber(risk.position_size, 4)}</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Leverage</div>
            <div className="tabular">{formatNumber(risk.leverage, 2)}x</div>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">VaR 95%</div>
            <div className="tabular">
              {risk.var_95 === null ? "—" : `${(risk.var_95 * 100).toFixed(2)}%`}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs">
          <div className="rounded-lg bg-muted/40 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">Stop loss</div>
            <div className="tabular text-bear">{formatPrice(risk.stop_loss)}</div>
          </div>
          <div className="rounded-lg bg-muted/40 px-3 py-2">
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
              Take profit
            </div>
            <div className="tabular text-bull">{formatPrice(risk.take_profit)}</div>
          </div>
        </div>

        <Separator />

        <ul className="space-y-2">
          {risk.checks.map((check) => (
            <li key={check.name} className="flex items-start gap-2 text-xs">
              <span className="mt-0.5">
                <CheckIcon passed={check.passed} blocking={check.blocking} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium capitalize">{check.name.replace(/_/g, " ")}</span>
                  {!check.blocking ? (
                    <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                      advisory
                    </span>
                  ) : null}
                </div>
                <div className="text-muted-foreground">{check.detail}</div>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </Panel>
  );
}
