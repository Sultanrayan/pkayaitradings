"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Check,
  CheckCircle2,
  Crown,
  Loader2,
  Minus,
  QrCode,
} from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";
import { Button } from "@/components/ui/button";
import { api, type PlanInfo } from "@/lib/api";

interface PlanCard {
  id: "free" | "pro" | "ultra";
  name: string;
  price: number;
  limit: number;
  blurb: string;
  featured?: boolean;
}

const PLANS: PlanCard[] = [
  {
    id: "free",
    name: "Free",
    price: 0,
    limit: 20,
    blurb: "20 analyses per month. Perfect for exploring.",
  },
  {
    id: "pro",
    name: "Pro",
    price: 15,
    limit: 150,
    blurb: "150 analyses per month for active traders. Try two months free.",
    featured: true,
  },
  {
    id: "ultra",
    name: "Ultra",
    price: 65,
    limit: -1,
    blurb: "Unlimited analyses for professionals.",
  },
];

const COMPARISON_ROWS: { label: string; free: string; pro: string; ultra: string }[] = [
  { label: "Analyses per month", free: "20", pro: "150", ultra: "Unlimited" },
  { label: "Multi-agent decisioning", free: "Yes", pro: "Yes", ultra: "Yes" },
  { label: "Live XAUUSD + BTCUSD", free: "Yes", pro: "Yes", ultra: "Yes" },
  { label: "Risk engine (VaR, stops)", free: "Yes", pro: "Yes", ultra: "Yes" },
  { label: "Order-flow & HMM regime", free: "—", pro: "Yes", ultra: "Yes" },
  { label: "Episodic memory + LLM review", free: "—", pro: "Yes", ultra: "Yes" },
  { label: "Support", free: "Community", pro: "Telegram", ultra: "Priority" },
  { label: "Price", free: "$0", pro: "$15", ultra: "$65" },
];

function Cell({ value }: { value: string }) {
  if (value === "Yes") return <Check className="mx-auto size-4 text-bull" />;
  if (value === "—") return <Minus className="mx-auto size-4 text-muted-foreground/50" />;
  return <span className="text-sm text-foreground">{value}</span>;
}

export function PricingView() {
  const router = useRouter();
  const { user } = useAuth();
  const [planInfo, setPlanInfo] = useState<PlanInfo | null>(null);
  const [trialLoading, setTrialLoading] = useState(false);

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

  const claimTrial = async () => {
    if (!user) {
      router.push("/login?next=/pricing");
      return;
    }
    setTrialLoading(true);
    try {
      const info = await api.billingTrial();
      setPlanInfo(info);
      toast.success("Pro activated — two months free!");
    } catch (cause) {
      toast.error(cause instanceof Error ? cause.message : "Could not activate the trial");
    } finally {
      setTrialLoading(false);
    }
  };

  const currentPlan = planInfo?.plan ?? (user ? "free" : null);
  const limit = planInfo?.limit ?? -1;
  const used = planInfo?.used ?? 0;
  const remaining = planInfo?.remaining ?? -1;
  const isEntitled = currentPlan === "pro" || currentPlan === "ultra";

  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="mx-auto max-w-6xl px-6 py-16">
        <div className="mx-auto mb-12 max-w-2xl text-center">
          <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">Pricing</p>
          <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight">
            Simple plans. Pay with KHQR.
          </h1>
          <p className="mt-4 text-sm text-muted-foreground">
            Free gets you 20 analyses a month. Try Pro free for two months, or compare all the
            plans below.
          </p>
        </div>

        {user && planInfo ? (
          <div className="mx-auto mb-12 flex max-w-2xl items-center justify-between rounded-2xl border border-border bg-card/60 px-6 py-4">
            <div>
              <p className="text-sm font-medium capitalize text-foreground">
                Your plan: {currentPlan}
              </p>
              <p className="text-xs text-muted-foreground">
                {limit === -1
                  ? "Unlimited analyses this period"
                  : `${used} of ${limit} analyses used this period (${Math.max(0, remaining)} left)`}
                {planInfo.expires_at
                  ? ` · renews ${new Date(planInfo.expires_at).toLocaleDateString()}`
                  : ""}
              </p>
            </div>
            <span className="rounded-full bg-bull/15 px-3 py-1 text-xs font-medium text-bull">
              Active
            </span>
          </div>
        ) : null}

        {/* Plan cards */}
        <div className="grid gap-6 md:grid-cols-3">
          {PLANS.map((plan) => {
            const isCurrent = currentPlan === plan.id;
            const isPro = plan.id === "pro";

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
            } else if (isPro) {
              actions = (
                <div className="space-y-2.5">
                  <Button className="w-full gap-2" disabled={trialLoading || isEntitled} onClick={claimTrial}>
                    {trialLoading ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Crown className="size-4" />
                    )}
                    Try 2 months free
                  </Button>
                  <Button asChild variant="outline" className="w-full gap-2">
                    <Link href={`/pricing/checkout?plan=${plan.id}`}>
                      <QrCode className="size-4" />
                      Upgrade Pro
                    </Link>
                  </Button>
                </div>
              );
            } else {
              actions = (
                <Button asChild className="w-full gap-2">
                  <Link href={`/pricing/checkout?plan=${plan.id}`}>
                    <QrCode className="size-4" />
                    {user ? `Upgrade · $${plan.price}` : "Sign in to upgrade"}
                  </Link>
                </Button>
              );
            }

            return (
              <div
                key={plan.id}
                className={`flex flex-col rounded-2xl border p-8 ${
                  plan.featured ? "border-[#003AF9]/40 bg-card" : "border-border bg-card/60"
                }`}
              >
                {plan.featured ? (
                  <span className="mb-3 inline-flex w-fit items-center gap-1.5 rounded-full bg-[#003AF9]/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#003AF9]">
                    <Crown className="size-3.5" />
                    Most popular
                  </span>
                ) : null}
                <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
                  {plan.name}
                </p>
                <div className="mt-4 flex items-baseline gap-1">
                  <span className="font-serif text-5xl font-medium tracking-tight text-foreground">
                    ${plan.price}
                  </span>
                  <span className="text-sm text-muted-foreground">/ 30 days</span>
                </div>
                <p className="mt-4 text-sm leading-relaxed text-muted-foreground">{plan.blurb}</p>
                <ul className="mt-6 flex-1 space-y-2 text-sm text-muted-foreground">
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="size-4 text-bull" />
                    {plan.limit === -1 ? "Unlimited analyses" : `${plan.limit} analyses per month`}
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="size-4 text-bull" />
                    All four agents
                  </li>
                  <li className="flex items-center gap-2">
                    <CheckCircle2 className="size-4 text-bull" />
                    Live XAUUSD + BTCUSD data
                  </li>
                </ul>
                <div className="mt-8">{actions}</div>
              </div>
            );
          })}
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

          <div className="mx-auto mt-10 max-w-3xl overflow-hidden rounded-2xl border border-border bg-card/60">
            <div className="grid grid-cols-[1.4fr_1fr_1fr_1fr] border-b border-border text-sm">
              <div className="p-4 text-muted-foreground">Plan</div>
              <div className="p-4 text-center font-medium text-foreground">Free</div>
              <div className="border-x border-border p-4 text-center font-medium text-[#003AF9]">
                Pro
              </div>
              <div className="p-4 text-center font-medium text-foreground">Ultra</div>
            </div>
            {COMPARISON_ROWS.map((row, index) => (
              <div
                key={row.label}
                className={`grid grid-cols-[1.4fr_1fr_1fr_1fr] text-sm ${
                  index !== COMPARISON_ROWS.length - 1 ? "border-b border-border" : ""
                }`}
              >
                <div className="p-4 text-muted-foreground">{row.label}</div>
                <div className="flex items-center justify-center p-4">
                  <Cell value={row.free} />
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