"use client";

import { useState } from "react";
import Link from "next/link";
import { cn } from "cn";

import { Button } from "@/components/ui/button";

/**
 * Pricing that prints like thermal receipts: a monospace ledger with dot
 * leaders, subtotal, a "months free" discount line, a barcode and serrated
 * edges. Switching monthly/yearly reprints the slips.
 * Adapted from the 21st.dev "Receipt Pricing" design.
 */

type Billing = "monthly" | "yearly";

interface LineItem {
  label: string;
  price: number;
}

interface Plan {
  name: string;
  tagline: string;
  monthly: number;
  items: LineItem[];
  cta: string;
  href: string;
  featured?: boolean;
}

const PLANS: Plan[] = [
  {
    name: "Free",
    tagline: "Paper trading",
    monthly: 0,
    items: [
      { label: "Paper trading", price: 0 },
      { label: "2 symbols", price: 0 },
      { label: "4 agents", price: 0 },
    ],
    cta: "Start free",
    href: "/register",
  },
  {
    name: "Pro",
    tagline: "Live analysis",
    monthly: 29,
    items: [
      { label: "Live market data", price: 12 },
      { label: "All four agents", price: 10 },
      { label: "Risk engine", price: 7 },
    ],
    cta: "Choose Pro",
    href: "/register",
    featured: true,
  },
  {
    name: "Enterprise",
    tagline: "Desks and teams",
    monthly: 99,
    items: [
      { label: "Unlimited symbols", price: 60 },
      { label: "Priority data", price: 25 },
      { label: "Support", price: 14 },
    ],
    cta: "Contact sales",
    href: "#",
  },
];

const MONTHS_FREE = 2;

function money(value: number): string {
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value)}`;
}

/** Deterministic bar widths so the barcode is stable per plan/billing. */
function barcodeBars(seed: string, count = 40): number[] {
  let hash = 2_166_136_261;
  for (let i = 0; i < seed.length; i += 1) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 16_777_619);
  }
  const bars: number[] = [];
  for (let i = 0; i < count; i += 1) {
    hash = (Math.imul(hash, 1_103_515_245) + 12_345) >>> 0;
    bars.push(1 + (hash % 3));
  }
  return bars;
}

function Barcode({ seed }: { seed: string }) {
  return (
    <div className="flex h-10 items-stretch justify-center gap-[2px]" aria-hidden>
      {barcodeBars(seed).map((width, index) => (
        <span
          key={index}
          className="bg-foreground"
          style={{ width: `${width}px`, opacity: index % 7 === 0 ? 0.7 : 1 }}
        />
      ))}
    </div>
  );
}

function Ledger({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span>{label}</span>
      <span className="flex-1 border-b border-dotted border-border" />
      <span className="tabular">{value}</span>
    </div>
  );
}

function Receipt({ plan, billing }: { plan: Plan; billing: Billing }) {
  const months = billing === "yearly" ? 12 : 1;
  const subtotal = plan.monthly * months;
  const discount = billing === "yearly" ? plan.monthly * MONTHS_FREE : 0;
  const total = subtotal - discount;

  return (
    <article
      className={cn(
        "receipt-edge receipt-print flex h-full flex-col gap-4 bg-card p-7 font-mono text-xs text-card-foreground",
        plan.featured && "bg-accent",
      )}
    >
      <header className="text-center">
        <p className="text-sm font-bold tracking-[0.25em]">PKAY TDAI</p>
        <p className="mt-1 text-[10px] uppercase tracking-widest text-muted-foreground">
          {billing === "yearly" ? "Annual plan" : "Monthly plan"}
        </p>
      </header>

      <div className="border-t border-dashed border-border" />

      <div className="space-y-1">
        <div className="flex items-center justify-between text-sm font-bold">
          <span>{plan.name}</span>
          {plan.featured ? (
            <span className="rounded-sm bg-foreground px-1.5 py-0.5 text-[9px] font-medium text-background">
              POPULAR
            </span>
          ) : null}
        </div>
        <p className="text-[10px] text-muted-foreground">{plan.tagline}</p>
      </div>

      <div className="space-y-2">
        {plan.items.map((item) => (
          <Ledger key={item.label} label={item.label} value={money(item.price * months)} />
        ))}
      </div>

      <div className="border-t border-dashed border-border" />

      <div className="space-y-2">
        <Ledger label="Subtotal" value={money(subtotal)} />
        {discount > 0 ? (
          <Ledger label={`${MONTHS_FREE} months free`} value={money(-discount)} />
        ) : null}
      </div>

      <div className="border-t border-dashed border-border" />

      <div className="flex items-baseline justify-between text-sm font-bold">
        <span>TOTAL</span>
        <span className="tabular">
          {money(total)}
          <span className="text-[10px] font-normal text-muted-foreground">
            {billing === "yearly" ? "/yr" : "/mo"}
          </span>
        </span>
      </div>

      <div className="mt-auto space-y-4 pt-2">
        <Barcode seed={`${plan.name}-${billing}`} />
        <Button
          asChild
          variant={plan.featured ? "default" : "outline"}
          className="w-full font-mono text-xs"
        >
          <Link href={plan.href}>{plan.cta}</Link>
        </Button>
      </div>
    </article>
  );
}

export function ReceiptPricing({ className }: { className?: string }) {
  const [billing, setBilling] = useState<Billing>("monthly");

  return (
    <div className={cn("w-full", className)}>
      <div className="mb-10 flex justify-center">
        <div
          role="group"
          aria-label="Billing period"
          className="inline-flex items-center gap-1 rounded-full border border-border p-1"
        >
          {(["monthly", "yearly"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={billing === option}
              onClick={() => setBilling(option)}
              className={cn(
                "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
                billing === option
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {option === "monthly" ? "Monthly" : "Yearly"}
              {option === "yearly" ? (
                <span className="ml-2 rounded-full bg-bull/15 px-1.5 py-0.5 text-[10px] text-bull">
                  {MONTHS_FREE} months free
                </span>
              ) : null}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {PLANS.map((plan) => (
          <Receipt key={`${plan.name}-${billing}`} plan={plan} billing={billing} />
        ))}
      </div>
    </div>
  );
}
