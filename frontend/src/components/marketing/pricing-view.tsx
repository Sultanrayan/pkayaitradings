"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { useAuth } from "@/components/auth-provider";
import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";
import { Button } from "@/components/ui/button";
import { api, type PlanInfo } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

type PlanId = "free" | "starter" | "pro" | "ultra";

interface PlanCard {
  id: PlanId;
  name: string;
  price: number;
  /** Analyses per UTC day. */
  dailyLimit: number;
  /** Analyses per 30-day billing period. */
  limit: number;
  blurb: string;
  features: string[];
  featured?: boolean;
}

const PLANS: PlanCard[] = [
  {
    id: "free",
    name: "Free",
    price: 0,
    dailyLimit: 2,
    limit: 60,
    blurb: "Explore the platform with 2 AI market analyses a day.",
    features: [
      "2 analyses per day",
      "60 analyses per month",
      "All four analysis agents",
      "Live XAUUSD + BTCUSD data",
    ],
  },
  {
    id: "starter",
    name: "Starter",
    price: 6,
    dailyLimit: 8,
    limit: 240,
    blurb: "For a regular cadence of analysis across both instruments.",
    features: [
      "8 analyses per day",
      "240 analyses per month",
      "All four analysis agents",
      "Live XAUUSD + BTCUSD data",
    ],
  },
  {
    id: "pro",
    name: "Pro",
    price: 13,
    dailyLimit: 20,
    limit: 600,
    blurb: "For active analysts who need deeper intelligence layers.",
    features: [
      "20 analyses per day",
      "600 analyses per month",
      "Order flow & regime detection",
      "Episodic memory + LLM review",
      "Telegram support",
    ],
    featured: true,
  },
  {
    id: "ultra",
    name: "Ultra",
    price: 250,
    dailyLimit: 250,
    limit: 7500,
    blurb: "High-volume analysis for professional market desks.",
    features: [
      "250 analyses per day",
      "7,500 analyses per month",
      "Every Pro intelligence layer",
      "Priority analyst support",
      "Early access to new models",
    ],
  },
];

const COMPARISON_ROWS: {
  label: string;
  free: string;
  starter: string;
  pro: string;
  ultra: string;
}[] = [
  { label: "Analyses per day", free: "2", starter: "8", pro: "20", ultra: "250" },
  { label: "Analyses per month", free: "60", starter: "240", pro: "600", ultra: "7,500" },
  { label: "Multi-agent decisioning", free: "Yes", starter: "Yes", pro: "Yes", ultra: "Yes" },
  { label: "Live XAUUSD + BTCUSD", free: "Yes", starter: "Yes", pro: "Yes", ultra: "Yes" },
  { label: "Risk engine (VaR, stops)", free: "Yes", starter: "Yes", pro: "Yes", ultra: "Yes" },
  { label: "Order-flow & HMM regime", free: "—", starter: "—", pro: "Yes", ultra: "Yes" },
  {
    label: "Episodic memory + LLM review",
    free: "—",
    starter: "—",
    pro: "Yes",
    ultra: "Yes",
  },
  {
    label: "Support",
    free: "Community",
    starter: "Community",
    pro: "Telegram",
    ultra: "Priority",
  },
  { label: "Price", free: "$0", starter: "$6", pro: "$13", ultra: "$250" },
];

/**
 * Comparison cell. Rendered as plain text so the table reads without icons;
 * an em dash carries the same "not included" meaning the minus icon did.
 */
function Cell({ value }: { value: string }) {
  if (value === "—") {
    return <span className="text-sm text-muted-foreground/50">—</span>;
  }
  return <span className="text-sm text-foreground">{value}</span>;
}

export function PricingView() {
  const { user } = useAuth();
  const [planInfo, setPlanInfo] = useState<PlanInfo | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      if (!user) return;
      try {
        const info = await api.billingPlan();
        if (active) setPlanInfo(info);
      } catch {
        if (active) setPlanInfo(null);
      }
    })();
    return () => {
      active = false;
    };
  }, [user]);

  const currentPlan = planInfo?.plan ?? (user ? "free" : null);
  const limit = planInfo?.limit ?? -1;
  const used = planInfo?.used ?? 0;
  const remaining = planInfo?.remaining ?? -1;
  const dailyLimit = planInfo?.daily_limit ?? -1;
  const usedToday = planInfo?.used_today ?? 0;
  const remainingToday = planInfo?.remaining_today ?? -1;

  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="mx-auto max-w-6xl px-6 py-16">
        {/* Section heading */}
        <div className="mx-auto mb-12 max-w-2xl text-center">
          <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
            Pricing plans
          </p>
          <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight">
            Transparent pricing, no surprises
          </h1>
          <p className="mt-4 text-sm text-muted-foreground">
            Every plan includes the four analysis agents and live market data. Higher tiers
            unlock the advanced intelligence layers.
          </p>
        </div>

        {user && planInfo ? (
          <div className="mx-auto mb-12 flex max-w-2xl items-center justify-between rounded-2xl border border-border bg-card/60 px-6 py-4">
            <div>
              <p className="text-sm font-medium capitalize text-foreground">
                Your plan: {currentPlan}
              </p>
              <p className="text-xs text-muted-foreground">
                {dailyLimit === -1
                  ? "No daily cap"
                  : `${usedToday} of ${dailyLimit} analyses used today (${Math.max(0, remainingToday)} left)`}
              </p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {limit === -1
                  ? "Unlimited analyses this period"
                  : `${used} of ${limit} analyses used this period (${Math.max(0, remaining)} left)`}
                {planInfo.expires_at
                  ? ` · renews ${formatDateTime(planInfo.expires_at)}`
                  : ""}
              </p>
            </div>
            <span className="rounded-full bg-bull/15 px-3 py-1 text-xs font-medium text-bull">
              Active
            </span>
          </div>
        ) : null}

        {/* Plan cards */}
        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-4">
          {PLANS.map((plan) => {
            const isCurrent = currentPlan === plan.id;

            let actions: React.ReactNode;
            if (isCurrent) {
              actions = (
                <Button disabled className="w-full">
                  Current plan
                </Button>
              );
            } else if (plan.id === "free") {
              actions = (
                <Button asChild className="w-full">
                  <Link href={user ? "/dashboard" : "/register"}>Start free</Link>
                </Button>
              );
            } else {
              actions = (
                <Button asChild className="w-full">
                  <Link href={`/pricing/checkout?plan=${plan.id}`}>
                    {user ? `Upgrade · $${plan.price}` : "Sign in to upgrade"}
                  </Link>
                </Button>
              );
            }

            return (
              <div
                key={plan.id}
                className={`flex flex-col rounded-2xl border p-7 ${
                  plan.featured ? "border-[#003AF9]/40 bg-card" : "border-border bg-card/60"
                }`}
              >
                {plan.featured ? (
                  <span className="mb-4 inline-flex w-fit items-center rounded-full bg-[#003AF9]/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#003AF9]">
                    Most popular
                  </span>
                ) : null}

                <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
                  {plan.name}
                </p>
                <div className="mt-3 flex items-baseline gap-1">
                  <span className="font-serif text-5xl font-medium tracking-tight text-foreground">
                    ${plan.price}
                  </span>
                  <span className="text-sm text-muted-foreground">/ 30 days</span>
                </div>

                <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{plan.blurb}</p>

                <ul className="mt-6 flex-1 list-disc space-y-2.5 pl-4 text-sm text-muted-foreground">
                  {plan.features.map((feature) => (
                    <li key={feature}>{feature}</li>
                  ))}
                </ul>

                <div className="mt-8">{actions}</div>
              </div>
            );
          })}
        </div>

        {/* Secondary upgrade path */}
        {PLANS.some((plan) => plan.id === "pro") ? (
          <div className="mt-6 flex flex-col gap-4 rounded-2xl border border-border bg-card/60 p-6 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-medium text-foreground">Prefer to pay directly?</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Upgrade Pro with a one-off payment.
              </p>
            </div>
            <Button asChild variant="outline" className="w-full shrink-0 sm:w-auto">
              <Link href={`/pricing/checkout?plan=pro`}>Upgrade Pro</Link>
            </Button>
          </div>
        ) : null}

        {/* Unique request */}
        <div className="mt-6 flex flex-col gap-4 rounded-2xl border border-border bg-card/60 p-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">Unique request</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Need a tailored analysis setup for your desk? Tell us what you need and we&apos;ll
              help you build it.
            </p>
          </div>
          <Button asChild variant="outline" className="w-full shrink-0 sm:w-auto">
            <Link href="/contact">Let&apos;s talk</Link>
          </Button>
        </div>

        {/* Comparison */}
        <section className="mt-20">
          <div className="mx-auto max-w-2xl text-center">
            <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
              Compare
            </p>
            <h2 className="mt-3 font-serif text-3xl font-medium tracking-tight">
              Compare the plans
            </h2>
            <p className="mt-4 text-sm text-muted-foreground">
              Every plan includes the four agents and live data. Higher tiers unlock advanced
              intelligence and support.
            </p>
          </div>

          <div className="mx-auto mt-10 max-w-4xl overflow-hidden rounded-2xl border border-border bg-card/60">
            <div className="grid grid-cols-[1.5fr_1fr_1fr_1fr_1fr] border-b border-border text-sm">
              <div className="p-4 text-muted-foreground">Plan</div>
              <div className="p-4 text-center font-medium text-foreground">Free</div>
              <div className="p-4 text-center font-medium text-foreground">Starter</div>
              <div className="border-x border-border p-4 text-center font-medium text-[#003AF9]">
                Pro
              </div>
              <div className="p-4 text-center font-medium text-foreground">Ultra</div>
            </div>
            {COMPARISON_ROWS.map((row, index) => (
              <div
                key={row.label}
                className={`grid grid-cols-[1.5fr_1fr_1fr_1fr_1fr] text-sm ${
                  index !== COMPARISON_ROWS.length - 1 ? "border-b border-border" : ""
                }`}
              >
                <div className="p-4 text-muted-foreground">{row.label}</div>
                <div className="flex items-center justify-center p-4">
                  <Cell value={row.free} />
                </div>
                <div className="flex items-center justify-center p-4">
                  <Cell value={row.starter} />
                </div>
                <div className="flex items-center justify-center border-x border-border p-4">
                  <Cell value={row.pro} />
                </div>
                <div className="flex items-center justify-center p-4">
                  <Cell value={row.ultra} />
                </div>
              </div>
            ))}
          </div>
        </section>

        <p className="mt-10 text-center text-xs text-muted-foreground">
          Prices are in USD. Access to the console requires a registered account. Payments are
          processed by Khpay.
        </p>
      </main>

      <FooterSection />
    </div>
  );
}
