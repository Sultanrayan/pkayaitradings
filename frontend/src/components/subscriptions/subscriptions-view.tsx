"use client";

import { useEffect, useState } from "react";
import { Check, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { PageHeader, ErrorNote, EmptyState } from "@/components/shared/primitives";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api, type PlanInfo } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

export function SubscriptionsView() {
  const [plan, setPlan] = useState<PlanInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      setLoading(true);
      try {
        const next = await api.billingPlan();
        if (active) {
          setPlan(next);
          setError(null);
        }
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Failed to load plan");
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const trial = async () => {
    try {
      setPlan(await api.billingTrial());
      toast.success("2-month Pro trial activated");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not activate trial");
    }
  };

  const catalogue = plan?.prices ?? {};
  const limits = plan?.limits ?? {};

  return (
    <div className="space-y-6">
      <PageHeader
        title="Subscriptions"
        description="Your plan, usage and upgrade options."
        actions={
          loading ? (
            <Loader2 className="size-4 animate-spin text-muted-foreground" />
          ) : (
            <Badge variant="outline" className="capitalize">
              {plan?.plan ?? "…"}
            </Badge>
          )
        }
      />

      {error ? <ErrorNote>{error}</ErrorNote> : null}

      {plan ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="capitalize">Current plan — {plan.plan}</CardTitle>
              <CardDescription>
                {plan.active
                  ? plan.expires_at
                    ? `Active until ${formatDateTime(plan.expires_at)}`
                    : "Active"
                  : "Plan not active"}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-end justify-between">
                <span className="text-2xl font-semibold tabular">{plan.remaining}</span>
                <span className="text-xs text-muted-foreground">analyses remaining</span>
              </div>
              {typeof plan.limit === "number" && plan.limit >= 0 ? (
                <div className="h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-foreground"
                    style={{
                      width: `${Math.min(100, (plan.used / plan.limit) * 100)}%`,
                    }}
                  />
                </div>
              ) : null}
              <div className="text-xs text-muted-foreground">
                Used {plan.used} of {plan.limit < 0 ? "unlimited" : plan.limit}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Usage limits</CardTitle>
              <CardDescription>Per billing period, across all symbols.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-1.5">
              {Object.entries(limits).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between text-sm">
                  <span className="capitalize text-muted-foreground">{key.replace(/_/g, " ")}</span>
                  <span className="tabular">{value < 0 ? "Unlimited" : value}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      ) : loading && !error ? (
        <EmptyState>Loading plan…</EmptyState>
      ) : null}

      {plan && ["free", "trial", ""].includes(plan.plan) ? (
        <Button onClick={trial}>Activate 2-month Pro trial</Button>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        {Object.entries(catalogue).map(([key, price]) => {
          const current = plan?.plan === key;
          return (
            <Card key={key} className={current ? "ring-1 ring-foreground/40" : ""}>
              <CardHeader>
                <CardTitle className="capitalize">{key}</CardTitle>
                <CardDescription>
                  {price === 0 ? "Free" : `$${price}/period`}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2 text-sm text-muted-foreground">
                <p className="flex items-center gap-2">
                  <Check className="size-4 text-bull" /> Multi-agent analysis
                </p>
                <p className="flex items-center gap-2">
                  <Check className="size-4 text-bull" /> Live market data
                </p>
                {current ? (
                  <div className="pt-1">
                    <Badge variant="outline">Current plan</Badge>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}